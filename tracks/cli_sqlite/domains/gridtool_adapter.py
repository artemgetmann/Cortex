"""gridtool domain adapter for the custom data processing CLI."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from tracks.cli_sqlite.domain_adapter import DomainWorkspace, ToolResult
from tracks.cli_sqlite.tool_aliases import ToolAlias


GRIDTOOL_PATH = Path(__file__).resolve().parent / "gridtool.py"

READ_SKILL_TOOL_NAME = "read_skill"
SHOW_FIXTURE_TOOL_NAME = "show_fixture"
RUN_GRIDTOOL_TOOL_NAME = "run_gridtool"

_GRIDTOOL_KEYWORDS = re.compile(
    r"(?i)\b(LOAD|KEEP|TOSS|TALLY|RANK|PICK|DERIVE|MERGE|SHOW|"
    r"eq|neq|gt|lt|gte|lte|sum|count|avg|min|max|asc|desc)\b"
)

_GRIDTOOL_ALIASES: dict[str, ToolAlias] = {
    "run_gridtool": ToolAlias(
        opaque_name="dispatch",
        canonical_name="run_gridtool",
        opaque_description="Execute a command against the workspace. Consult skill docs for parameter semantics.",
        canonical_description="Execute gridtool commands against CSV data. Pass commands as a string.",
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
    alias = _GRIDTOOL_ALIASES.get(canonical)
    if alias is None:
        return canonical
    return alias.opaque_name if opaque else canonical


def _get_tool_description(canonical: str, opaque: bool) -> str:
    alias = _GRIDTOOL_ALIASES.get(canonical)
    if alias is None:
        return ""
    return alias.opaque_description if opaque else alias.canonical_description


class GridtoolAdapter:
    """DomainAdapter implementation for the custom gridtool CLI."""

    def __init__(self, *, cryptic_errors: bool = False) -> None:
        self._cryptic = cryptic_errors

    @property
    def name(self) -> str:
        return "gridtool"

    @property
    def executor_tool_name(self) -> str:
        return RUN_GRIDTOOL_TOOL_NAME

    def tool_defs(self, fixture_refs: list[str], *, opaque: bool) -> list[dict[str, Any]]:
        refs_text = ", ".join(fixture_refs) if fixture_refs else "(none)"
        show_desc = _get_tool_description("show_fixture", opaque)
        return [
            {
                "name": _get_tool_api_name("run_gridtool", opaque),
                "description": _get_tool_description("run_gridtool", opaque),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "commands": {"type": "string", "description": "gridtool commands to execute (one per line)."}
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
            return ToolResult(error=f"run_gridtool requires string commands, got {commands!r}")
        try:
            cmd = ["python3", str(GRIDTOOL_PATH), "--workdir", str(workspace.work_dir)]
            if self._cryptic:
                cmd.append("--cryptic")
            result = subprocess.run(
                cmd,
                input=commands,
                capture_output=True,
                text=True,
                timeout=5.0,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(error="gridtool timed out after 5.0s")
        except FileNotFoundError:
            return ToolResult(error="python3 or gridtool.py not found")
        except Exception as exc:
            return ToolResult(error=f"gridtool execution failed: {type(exc).__name__}: {exc}")

        if result.returncode == 0:
            return ToolResult(output=result.stdout.strip() or "(ok)")
        return ToolResult(error=result.stderr.strip() or f"gridtool exited with code {result.returncode}")

    def prepare_workspace(self, task_dir: Path, work_dir: Path) -> DomainWorkspace:
        work_dir.mkdir(parents=True, exist_ok=True)
        # Copy fixture files into work_dir so gridtool can find them
        fixture_paths: dict[str, Path] = {}
        import shutil
        for csv_path in sorted(task_dir.glob("*.csv")):
            dest = work_dir / csv_path.name
            shutil.copy2(csv_path, dest)
            fixture_paths[csv_path.name] = csv_path  # reference original for show_fixture
        # Also track task.md if present
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
        # For gridtool, the final state is best captured from event logs
        # since output goes to stdout. Return a hint.
        return "See event log for gridtool SHOW outputs."

    def system_prompt_fragment(self) -> str:
        return (
            "You are controlling a gridtool CLI environment.\n"
            "gridtool is a data processing tool with its own syntax.\n"
            "You MUST read the skill doc before using it — the syntax is NOT SQL.\n"
            "Rules:\n"
            "- Use run_gridtool to execute gridtool commands.\n"
            "- You must read at least one routed skill with read_skill before run_gridtool.\n"
            "- Use read_skill whenever routed skill summaries are insufficient for exact execution.\n"
            "- Use show_fixture to inspect fixture files.\n"
            "- gridtool commands: LOAD, KEEP, TOSS, TALLY, RANK, PICK, DERIVE, MERGE, SHOW.\n"
            "- Do NOT use SQL syntax — gridtool is completely different.\n"
        )

    def quality_keywords(self) -> re.Pattern[str]:
        return _GRIDTOOL_KEYWORDS

    def build_alias_map(self, *, opaque: bool) -> dict[str, str]:
        result: dict[str, str] = {}
        for canonical, alias in _GRIDTOOL_ALIASES.items():
            api_name = alias.opaque_name if opaque else canonical
            result[api_name] = canonical
        return result
