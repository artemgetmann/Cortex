"""Shell domain adapter for generic command execution tasks."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from tracks.cli_sqlite.domain_adapter import DomainDoc, DomainWorkspace, ToolResult
from tracks.cli_sqlite.tool_aliases import ToolAlias


READ_SKILL_TOOL_NAME = "read_skill"
SHOW_FIXTURE_TOOL_NAME = "show_fixture"
RUN_BASH_TOOL_NAME = "run_bash"

_SHELL_KEYWORDS = re.compile(
    r"(?i)\b("
    r"bash|python|python3|pip|module|traceback|stderr|exit code|"
    r"xlsx|excel|worksheet|workbook|openpyxl|xlsxwriter|pandas|csv|json|"
    r"chmod|ls|cat|cp|mv|mkdir|rm|sed|awk|grep|rg|curl"
    r")\b"
)

_SHELL_ALIASES: dict[str, ToolAlias] = {
    "run_bash": ToolAlias(
        opaque_name="dispatch",
        canonical_name="run_bash",
        opaque_description="Execute a command against the workspace. Consult skill docs for parameter semantics.",
        canonical_description="Execute shell command(s) in a task-local working directory.",
    ),
    "read_skill": ToolAlias(
        opaque_name="probe",
        canonical_name="read_skill",
        opaque_description="Look up a reference document by ref key.",
        canonical_description="Read full contents of a skill document by stable skill_ref.",
    ),
    "show_fixture": ToolAlias(
        opaque_name="catalog",
        canonical_name="show_fixture",
        opaque_description="Retrieve a named data artifact.",
        canonical_description="Read task fixture/bootstrap file by stable path_ref.",
    ),
}


def _get_tool_api_name(canonical: str, opaque: bool) -> str:
    alias = _SHELL_ALIASES.get(canonical)
    if alias is None:
        return canonical
    return alias.opaque_name if opaque else canonical


def _get_tool_description(canonical: str, opaque: bool) -> str:
    alias = _SHELL_ALIASES.get(canonical)
    if alias is None:
        return ""
    return alias.opaque_description if opaque else alias.canonical_description


def _clip_text(text: str, *, max_chars: int = 1800) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3] + "..."


def _inspect_xlsx(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {
        "name": path.name,
        "size_bytes": int(path.stat().st_size),
        "sheet_names": [],
        "worksheet_row_counts": {},
        "error": None,
    }
    try:
        with zipfile.ZipFile(path, "r") as zf:
            workbook_xml = zf.read("xl/workbook.xml")
            tree = ET.fromstring(workbook_xml)
            ns = {"ss": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            sheet_nodes = tree.findall(".//ss:sheets/ss:sheet", ns)
            info["sheet_names"] = [str(node.attrib.get("name", "")).strip() for node in sheet_nodes if node.attrib.get("name")]

            worksheet_paths = sorted(
                name for name in zf.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
            )
            row_counts: dict[str, int] = {}
            for worksheet_path in worksheet_paths[:10]:
                try:
                    row_counts[Path(worksheet_path).name] = zf.read(worksheet_path).count(b"<row")
                except Exception:
                    row_counts[Path(worksheet_path).name] = -1
            info["worksheet_row_counts"] = row_counts
    except Exception as exc:
        info["error"] = f"{type(exc).__name__}: {exc}"
    return info


class ShellAdapter:
    """DomainAdapter implementation for shell-command tasks."""

    @property
    def name(self) -> str:
        return "shell"

    @property
    def executor_tool_name(self) -> str:
        return RUN_BASH_TOOL_NAME

    def tool_defs(self, fixture_refs: list[str], *, opaque: bool) -> list[dict[str, Any]]:
        refs_text = ", ".join(fixture_refs) if fixture_refs else "(none)"
        show_desc = _get_tool_description("show_fixture", opaque)
        return [
            {
                "name": _get_tool_api_name("run_bash", opaque),
                "description": _get_tool_description("run_bash", opaque),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Shell command(s) to execute in the task workspace.",
                        }
                    },
                    "required": ["command"],
                    "additionalProperties": False,
                },
            },
            {
                "name": _get_tool_api_name("read_skill", opaque),
                "description": _get_tool_description("read_skill", opaque),
                "input_schema": {
                    "type": "object",
                    "properties": {"skill_ref": {"type": "string"}},
                    "required": ["skill_ref"],
                    "additionalProperties": False,
                },
            },
            {
                "name": _get_tool_api_name("show_fixture", opaque),
                "description": f"{show_desc} Available refs: {refs_text}.",
                "input_schema": {
                    "type": "object",
                    "properties": {"path_ref": {"type": "string"}},
                    "required": ["path_ref"],
                    "additionalProperties": False,
                },
            },
        ]

    def execute(self, tool_name: str, tool_input: dict[str, Any], workspace: DomainWorkspace) -> ToolResult:
        command = tool_input.get("command")
        if not isinstance(command, str) or not command.strip():
            return ToolResult(error=f"run_bash requires non-empty string command, got {command!r}")
        try:
            result = subprocess.run(
                ["/bin/bash", "-lc", command],
                cwd=str(workspace.work_dir),
                capture_output=True,
                text=True,
                timeout=45.0,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = _clip_text(exc.stdout or "")
            stderr = _clip_text(exc.stderr or "")
            detail = f"stdout={stdout!r} stderr={stderr!r}" if stdout or stderr else "no output"
            return ToolResult(error=f"run_bash timed out after 45.0s: {detail}")
        except FileNotFoundError:
            return ToolResult(error="run_bash failed: /bin/bash not found")
        except Exception as exc:
            return ToolResult(error=f"run_bash failed: {type(exc).__name__}: {exc}")

        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        if result.returncode != 0:
            primary = stderr or stdout or "(no output)"
            return ToolResult(
                error=f"run_bash exited with code {result.returncode}: {_clip_text(primary)}"
            )

        payload = {
            "returncode": int(result.returncode),
            "stdout": _clip_text(stdout, max_chars=2200) if stdout else "",
            "stderr": _clip_text(stderr, max_chars=1200) if stderr else "",
        }
        return ToolResult(output=json.dumps(payload, ensure_ascii=True, sort_keys=True))

    def prepare_workspace(self, task_dir: Path, work_dir: Path) -> DomainWorkspace:
        work_dir.mkdir(parents=True, exist_ok=True)
        fixture_paths: dict[str, Path] = {}
        for file_path in sorted(task_dir.iterdir()):
            if not file_path.is_file():
                continue
            if file_path.name == "CONTRACT.json":
                continue
            fixture_paths[file_path.name] = file_path
            if file_path.name == "task.md":
                continue
            shutil.copy2(file_path, work_dir / file_path.name)
        return DomainWorkspace(
            task_id=task_dir.name,
            task_dir=task_dir,
            work_dir=work_dir,
            fixture_paths=fixture_paths,
        )

    def capture_final_state(self, workspace: DomainWorkspace) -> str:
        rows: dict[str, Any] = {
            "workspace": str(workspace.work_dir),
            "files": [],
            "xlsx": [],
            "last_successful_output": "",
        }
        file_rows: list[dict[str, Any]] = []
        for path in sorted(workspace.work_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = str(path.relative_to(workspace.work_dir))
            file_rows.append({"path": rel, "size_bytes": int(path.stat().st_size)})
        rows["files"] = file_rows[:80]

        for file_row in file_rows:
            rel_path = str(file_row.get("path", ""))
            if not rel_path.lower().endswith(".xlsx"):
                continue
            rows["xlsx"].append(_inspect_xlsx(workspace.work_dir / rel_path))

        events_path = workspace.work_dir / "events.jsonl"
        if events_path.exists():
            for line in events_path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if row.get("tool") == RUN_BASH_TOOL_NAME and row.get("ok") and row.get("output"):
                    rows["last_successful_output"] = str(row["output"])[:2200]
        return json.dumps(rows, ensure_ascii=True, sort_keys=True)

    def system_prompt_fragment(self) -> str:
        return (
            "You are controlling a shell workspace.\n"
            "Rules:\n"
            "- Use run_bash for command execution.\n"
            "- run_bash runs in a task-local working directory.\n"
            "- Use show_fixture to inspect task files before writing scripts.\n"
            "- You may use python3 from run_bash when needed.\n"
            "- Keep commands deterministic and verify results with explicit checks.\n"
        )

    def quality_keywords(self) -> re.Pattern[str]:
        return _SHELL_KEYWORDS

    def build_alias_map(self, *, opaque: bool) -> dict[str, str]:
        result: dict[str, str] = {}
        for canonical, alias in _SHELL_ALIASES.items():
            api_name = alias.opaque_name if opaque else canonical
            result[api_name] = canonical
        return result

    def docs_manifest(self) -> list[DomainDoc]:
        return []
