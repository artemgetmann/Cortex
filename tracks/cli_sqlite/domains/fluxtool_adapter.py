"""fluxtool domain adapter for holdout transfer validation."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from tracks.cli_sqlite.domain_adapter import DomainDoc, DomainWorkspace, ToolResult
from tracks.cli_sqlite.tool_aliases import ToolAlias


FLUXTOOL_PATH = Path(__file__).resolve().parent / "fluxtool.py"
FLUXTOOL_DOCS_DIR = Path(__file__).resolve().parent / "docs"

READ_SKILL_TOOL_NAME = "read_skill"
SHOW_FIXTURE_TOOL_NAME = "show_fixture"
RUN_FLUXTOOL_TOOL_NAME = "run_fluxtool"

_FLUXTOOL_KEYWORDS = re.compile(
    r"(?i)\b(IMPORT|FILTER|EXCLUDE|GROUP|SORT|COLUMNS|COMPUTE|ATTACH|DISPLAY|"
    r"is|isnt|above|below|atleast|atmost|sum|count|avg|min|max|up|down)\b"
)

_FLUXTOOL_ALIASES: dict[str, ToolAlias] = {
    "run_fluxtool": ToolAlias(
        opaque_name="dispatch",
        canonical_name="run_fluxtool",
        opaque_description="Execute a command against the workspace. Consult skill docs for parameter semantics.",
        canonical_description="Execute fluxtool commands against CSV data. Pass commands as a string.",
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

DEFAULT_MIXED_ERROR_MODE_MAP: dict[str, str] = {
    "IMPORT": "semi",
    "EXCLUDE": "semi",
    "DISPLAY": "semi",
    "GROUP": "cryptic",
    "ATTACH": "cryptic",
    "COMPUTE": "cryptic",
    "FILTER": "cryptic",
    "SORT": "cryptic",
    "COLUMNS": "cryptic",
}


def _get_tool_api_name(canonical: str, opaque: bool) -> str:
    alias = _FLUXTOOL_ALIASES.get(canonical)
    if alias is None:
        return canonical
    return alias.opaque_name if opaque else canonical


def _get_tool_description(canonical: str, opaque: bool) -> str:
    alias = _FLUXTOOL_ALIASES.get(canonical)
    if alias is None:
        return ""
    return alias.opaque_description if opaque else alias.canonical_description


class FluxtoolAdapter:
    """DomainAdapter implementation for holdout fluxtool CLI."""

    def __init__(
        self,
        *,
        cryptic_errors: bool = False,
        semi_helpful_errors: bool = False,
        mixed_errors: bool = False,
        error_mode_map: dict[str, str] | None = None,
    ) -> None:
        self._cryptic = cryptic_errors
        self._semi_helpful = semi_helpful_errors
        if error_mode_map:
            self._error_mode_map = {str(k).upper(): str(v).lower() for k, v in error_mode_map.items()}
        elif mixed_errors:
            self._error_mode_map = dict(DEFAULT_MIXED_ERROR_MODE_MAP)
        else:
            self._error_mode_map = {}

    @property
    def name(self) -> str:
        return "fluxtool"

    @property
    def executor_tool_name(self) -> str:
        return RUN_FLUXTOOL_TOOL_NAME

    def tool_defs(self, fixture_refs: list[str], *, opaque: bool) -> list[dict[str, Any]]:
        refs_text = ", ".join(fixture_refs) if fixture_refs else "(none)"
        show_desc = _get_tool_description("show_fixture", opaque)
        return [
            {
                "name": _get_tool_api_name("run_fluxtool", opaque),
                "description": _get_tool_description("run_fluxtool", opaque),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "commands": {"type": "string", "description": "fluxtool commands to execute (one per line)."}
                    },
                    "required": ["commands"],
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
        commands = tool_input.get("commands")
        if not isinstance(commands, str):
            return ToolResult(error=f"run_fluxtool requires string commands, got {commands!r}")
        try:
            # Adapter delegates execution to fluxtool wrapper, which in turn
            # translates to gridtool and maps outputs/errors back to holdout
            # vocabulary. This isolates holdout remapping in one place.
            cmd = ["python3", str(FLUXTOOL_PATH), "--workdir", str(workspace.work_dir)]
            if self._cryptic:
                cmd.append("--cryptic")
            elif self._semi_helpful:
                cmd.append("--semi-helpful")
            if self._error_mode_map:
                map_text = ",".join(f"{cmd_name}={mode}" for cmd_name, mode in sorted(self._error_mode_map.items()))
                cmd.extend(["--error-mode-map", map_text])
            result = subprocess.run(
                cmd,
                input=commands,
                capture_output=True,
                text=True,
                timeout=5.0,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(error="fluxtool timed out after 5.0s")
        except FileNotFoundError:
            return ToolResult(error="python3 or fluxtool.py not found")
        except Exception as exc:
            return ToolResult(error=f"fluxtool execution failed: {type(exc).__name__}: {exc}")

        if result.returncode == 0:
            return ToolResult(output=result.stdout.strip() or "(ok)")
        return ToolResult(error=result.stderr.strip() or f"fluxtool exited with code {result.returncode}")

    def prepare_workspace(self, task_dir: Path, work_dir: Path) -> DomainWorkspace:
        work_dir.mkdir(parents=True, exist_ok=True)
        fixture_paths: dict[str, Path] = {}
        import shutil

        # Mirror gridtool workspace behavior so transfer comparisons isolate
        # syntax remapping effects rather than filesystem/environment drift.
        for csv_path in sorted(task_dir.glob("*.csv")):
            dest = work_dir / csv_path.name
            shutil.copy2(csv_path, dest)
            fixture_paths[csv_path.name] = csv_path
        task_md = task_dir / "task.md"
        if task_md.exists():
            fixture_paths["task.md"] = task_md
        return DomainWorkspace(
            task_id=task_dir.name,
            task_dir=task_dir,
            work_dir=work_dir,
            fixture_paths=fixture_paths,
        )

    def capture_final_state(self, workspace: DomainWorkspace) -> str:
        events_path = workspace.work_dir / "events.jsonl"
        if not events_path.exists():
            return "(no events recorded)"
        import json

        last_output = None
        for line in events_path.read_text(encoding="utf-8").splitlines():
            try:
                evt = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if evt.get("tool") == "run_fluxtool" and evt.get("ok") and evt.get("output"):
                last_output = evt["output"]
        if last_output:
            return f"Last successful fluxtool output:\n{last_output[:2000]}"
        return "(no successful fluxtool output)"

    def system_prompt_fragment(self) -> str:
        return (
            "You are controlling a fluxtool CLI environment.\n"
            "fluxtool is a holdout data-processing DSL with remapped syntax — NOT SQL.\n"
            "Rules:\n"
            "- Use run_fluxtool to execute fluxtool commands.\n"
            "- Use show_fixture to inspect fixture files.\n"
            "- Before starting, check the Skills metadata section. If a skill's title or\n"
            "  description seems relevant to your task, read it with read_skill using the\n"
            "  exact skill_ref listed. Only call read_skill with refs that are listed —\n"
            "  do not guess or invent skill_ref names.\n"
            "- fluxtool commands: IMPORT, FILTER, EXCLUDE, GROUP, SORT, COLUMNS, COMPUTE, ATTACH, DISPLAY.\n"
            "- Do NOT use SQL syntax and do NOT assume gridtool command names.\n"
        )

    def quality_keywords(self) -> re.Pattern[str]:
        return _FLUXTOOL_KEYWORDS

    def build_alias_map(self, *, opaque: bool) -> dict[str, str]:
        result: dict[str, str] = {}
        for canonical, alias in _FLUXTOOL_ALIASES.items():
            api_name = alias.opaque_name if opaque else canonical
            result[api_name] = canonical
        return result

    def docs_manifest(self) -> list[DomainDoc]:
        # Strict-mode critic retrieval consumes this manifest. Keep it short and
        # domain-focused to avoid irrelevant context leakage from other domains.
        docs = [
            DomainDoc(
                doc_id="fluxtool/reference",
                path=FLUXTOOL_DOCS_DIR / "fluxtool-reference.md",
                title="Fluxtool Syntax Reference",
                tags=("fluxtool", "import", "group", "compute", "attach", "display"),
            )
        ]
        return [doc for doc in docs if doc.path.exists()]
