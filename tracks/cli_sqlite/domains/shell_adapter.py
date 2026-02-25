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
SHELL_DOCS_DIR = Path(__file__).resolve().parent / "docs"

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

_HOTFIX_HARD_TASK_ID = "shell_git_transfer_hotfix_hard"
_HOTFIX_HARD_VARIANTS: tuple[dict[str, str], ...] = (
    {
        "variant_id": "alpha",
        "patch_file": "hotfix_alpha.patch",
        "hotfix_file": "hotfix_alpha.txt",
        "commit_message": "hotfix: apply alpha retry profile",
        "marker_line": "Retry profile alpha",
        "change_line": "Set initial delay to 275ms",
    },
    {
        "variant_id": "beta",
        "patch_file": "hotfix_beta.patch",
        "hotfix_file": "hotfix_beta.txt",
        "commit_message": "hotfix: apply beta retry profile",
        "marker_line": "Retry profile beta",
        "change_line": "Set initial delay to 300ms",
    },
    {
        "variant_id": "gamma",
        "patch_file": "hotfix_gamma.patch",
        "hotfix_file": "hotfix_gamma.txt",
        "commit_message": "hotfix: apply gamma retry profile",
        "marker_line": "Retry profile gamma",
        "change_line": "Set initial delay to 325ms",
    },
)


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


def _extract_session_id(work_dir: Path) -> int:
    # Session directories are created as `session-<id>` by the CLI harness.
    # We parse the numeric suffix to deterministically select task variants.
    match = re.search(r"session-(\d+)", str(work_dir))
    if not match:
        return 0
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return 0


def _select_hotfix_variant(session_id: int) -> dict[str, str]:
    if not _HOTFIX_HARD_VARIANTS:
        raise RuntimeError("No hotfix variants configured for shell_git_transfer_hotfix_hard.")
    if session_id <= 0:
        return dict(_HOTFIX_HARD_VARIANTS[0])
    idx = int(session_id) % len(_HOTFIX_HARD_VARIANTS)
    return dict(_HOTFIX_HARD_VARIANTS[idx])


def _replace_tokens(payload: Any, replacements: dict[str, str]) -> Any:
    if isinstance(payload, str):
        out = payload
        for token, value in replacements.items():
            out = out.replace(token, value)
        return out
    if isinstance(payload, list):
        return [_replace_tokens(item, replacements) for item in payload]
    if isinstance(payload, dict):
        return {str(key): _replace_tokens(value, replacements) for key, value in payload.items()}
    return payload


def _build_hotfix_hard_runtime_artifacts(
    *,
    task_dir: Path,
    work_dir: Path,
) -> tuple[dict[str, Path], dict[str, Any]]:
    session_id = _extract_session_id(work_dir)
    variant = _select_hotfix_variant(session_id)
    transfer_branch = "main"
    variant_id = str(variant["variant_id"])
    patch_file = str(variant["patch_file"])
    hotfix_file = str(variant["hotfix_file"])
    commit_message = str(variant["commit_message"])
    marker_line = str(variant["marker_line"])
    change_line = str(variant["change_line"])
    verification_line = (
        f"GIT_TRANSFER_OK target=target_repo branch={transfer_branch} "
        f"patches=1 file={hotfix_file} variant={variant_id}"
    )
    summary_lines = [
        f"TRANSFER_BRANCH {transfer_branch}",
        "TRANSFER_PATCHES 1",
        f"TRANSFER_PATCH_FILE {patch_file}",
        f"TRANSFER_VARIANT {variant_id}",
    ]
    payload_lines: list[str] = []
    payload_path = task_dir / "hotfix_payload.txt"
    if payload_path.exists():
        payload_lines = [
            str(line).strip()
            for line in payload_path.read_text(encoding="utf-8", errors="replace").splitlines()
            if str(line).strip()
        ]
    if marker_line not in payload_lines:
        payload_lines.append(marker_line)
    if change_line not in payload_lines:
        payload_lines.append(change_line)

    variant_spec = {
        "task_id": _HOTFIX_HARD_TASK_ID,
        "session_id": session_id,
        "variant_id": variant_id,
        "source_repo": "source_repo",
        "target_repo": "target_repo",
        "transfer_branch": transfer_branch,
        "patch_file": patch_file,
        "hotfix_file": hotfix_file,
        "commit_message": commit_message,
        "required_marker_line": marker_line,
        "required_change_line": change_line,
        "summary_lines": summary_lines,
        "verification_line": verification_line,
        "hotfix_lines": payload_lines,
    }
    variant_spec_path = work_dir / "variant_spec.json"
    variant_spec_path.write_text(json.dumps(variant_spec, ensure_ascii=True, indent=2), encoding="utf-8")

    contract_template_path = task_dir / "CONTRACT.json"
    runtime_contract_path = work_dir / "CONTRACT.runtime.json"
    if contract_template_path.exists():
        try:
            contract_template = json.loads(contract_template_path.read_text(encoding="utf-8"))
        except Exception:
            contract_template = {}
        if isinstance(contract_template, dict):
            replacements = {
                "__PATCH_FILE__": patch_file,
                "__HOTFIX_FILE__": hotfix_file,
                "__COMMIT_MESSAGE__": commit_message,
                "__TRANSFER_BRANCH__": transfer_branch,
                "__VARIANT_ID__": variant_id,
                "__VERIFICATION_LINE__": verification_line,
                "__MARKER_LINE__": marker_line,
                "__CHANGE_LINE__": change_line,
            }
            runtime_contract = _replace_tokens(contract_template, replacements)
            runtime_contract_path.write_text(
                json.dumps(runtime_contract, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )

    runtime_brief_path = work_dir / "runtime_task.md"
    runtime_brief_path.write_text(
        (
            "# Runtime Variant\n\n"
            "Read `variant_spec.json` and follow it exactly.\n"
            f"- variant_id: {variant_id}\n"
            f"- hotfix_file: {hotfix_file}\n"
            f"- patch_file: {patch_file}\n"
            f"- commit_message: {commit_message}\n"
        ),
        encoding="utf-8",
    )
    return (
        {
            "variant_spec.json": variant_spec_path,
            "runtime_task.md": runtime_brief_path,
            "CONTRACT.runtime.json": runtime_contract_path,
        },
        variant_spec,
    )


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
        if task_dir.name == _HOTFIX_HARD_TASK_ID:
            runtime_paths, _ = _build_hotfix_hard_runtime_artifacts(task_dir=task_dir, work_dir=work_dir)
            for ref, path in runtime_paths.items():
                if path.exists():
                    fixture_paths[ref] = path
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
        docs = [
            DomainDoc(
                doc_id="shell/git-reference",
                path=SHELL_DOCS_DIR / "shell-git-reference.md",
                title="Shell Git Reference",
                tags=("shell", "git", "commit", "branch", "merge", "patch"),
            ),
            DomainDoc(
                doc_id="shell/xlsx-reference",
                path=SHELL_DOCS_DIR / "shell-xlsx-reference.md",
                title="Shell XLSX Reference",
                tags=("shell", "python", "openpyxl", "xlsx", "summary", "csv"),
            ),
        ]
        return [doc for doc in docs if doc.path.exists()]
