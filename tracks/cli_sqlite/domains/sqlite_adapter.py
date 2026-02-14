"""SQLite domain adapter — wraps existing executor.py into the DomainAdapter protocol."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from tracks.cli_sqlite.domain_adapter import DomainAdapter, DomainWorkspace, ToolResult
from tracks.cli_sqlite.executor import (
    TaskWorkspace,
    prepare_task_workspace,
    run_sqlite,
    show_fixture_text,
)
from tracks.cli_sqlite.tool_aliases import ToolAlias


# Tool constants
READ_SKILL_TOOL_NAME = "read_skill"
SHOW_FIXTURE_TOOL_NAME = "show_fixture"
RUN_SQLITE_TOOL_NAME = "run_sqlite"

# Re-use the existing SQL keywords regex from learning_cli.py
_SQL_KEYWORDS = re.compile(
    r"(?i)\b("
    r"SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|BEGIN|COMMIT|ROLLBACK|"
    r"ON CONFLICT|GROUP BY|ORDER BY|WHERE|JOIN|PRIMARY KEY|FOREIGN KEY|"
    r"INTEGER|TEXT|REAL|BLOB|NULL|NOT NULL|UNIQUE|INDEX|TRANSACTION|"
    r"SUM|COUNT|AVG|MAX|MIN|HAVING|DISTINCT|UNION|EXCEPT|INTERSECT|"
    r"VALUES|INTO|FROM|TABLE|VIEW|TRIGGER|"
    r"fixture_seed|ledger|rejects|checkpoint_log|sales|error_log|inventory"
    r")\b"
)

# Standard tool aliases for sqlite domain
_SQLITE_ALIASES: dict[str, ToolAlias] = {
    "run_sqlite": ToolAlias(
        opaque_name="dispatch",
        canonical_name="run_sqlite",
        opaque_description="Execute a command against the workspace. Consult skill docs for parameter semantics.",
        canonical_description="Execute SQL against task-local sqlite database. No shell escapes. Dot-commands are restricted.",
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
    alias = _SQLITE_ALIASES.get(canonical)
    if alias is None:
        return canonical
    return alias.opaque_name if opaque else canonical


def _get_tool_description(canonical: str, opaque: bool) -> str:
    alias = _SQLITE_ALIASES.get(canonical)
    if alias is None:
        return ""
    return alias.opaque_description if opaque else alias.canonical_description


class SqliteAdapter:
    """DomainAdapter implementation for SQLite CLI tasks."""

    @property
    def name(self) -> str:
        return "sqlite"

    @property
    def executor_tool_name(self) -> str:
        return RUN_SQLITE_TOOL_NAME

    def tool_defs(self, fixture_refs: list[str], *, opaque: bool) -> list[dict[str, Any]]:
        refs_text = ", ".join(fixture_refs) if fixture_refs else "(none)"
        show_desc = _get_tool_description("show_fixture", opaque)
        return [
            {
                "name": _get_tool_api_name("run_sqlite", opaque),
                "description": _get_tool_description("run_sqlite", opaque),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "sql": {"type": "string", "description": "SQL (or safe .read) to execute via sqlite3."}
                    },
                    "required": ["sql"],
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
        sql = tool_input.get("sql")
        if not isinstance(sql, str):
            return ToolResult(error=f"run_sqlite requires string sql, got {sql!r}")
        allowed_read_paths = {path.resolve() for path in workspace.fixture_paths.values()}
        exec_result = run_sqlite(
            db_path=workspace.work_dir / "task.db",
            sql=sql,
            timeout_s=5.0,
            allowed_read_paths=allowed_read_paths,
        )
        if exec_result.ok:
            payload = exec_result.output or "(ok)"
            return ToolResult(output=payload)
        return ToolResult(error=exec_result.error)

    def prepare_workspace(self, task_dir: Path, work_dir: Path) -> DomainWorkspace:
        db_path = work_dir / "task.db"
        # Delegate to existing prepare_task_workspace which creates DB + loads fixtures
        track_root = task_dir.parent.parent  # tasks/<task_id> -> track root
        task_id = task_dir.name
        tw = prepare_task_workspace(track_root=track_root, task_id=task_id, db_path=db_path)
        return DomainWorkspace(
            task_id=tw.task_id,
            task_dir=tw.task_dir,
            work_dir=work_dir,
            fixture_paths=tw.fixture_paths,
        )

    def capture_final_state(self, workspace: DomainWorkspace) -> str:
        db_path = workspace.work_dir / "task.db"
        if not db_path.exists():
            return "(no database file)"
        try:
            with sqlite3.connect(str(db_path)) as conn:
                lines: list[str] = []
                for line in conn.iterdump():
                    lines.append(line)
                return "\n".join(lines[-50:]) if len(lines) > 50 else "\n".join(lines)
        except Exception as exc:
            return f"(dump failed: {type(exc).__name__}: {exc})"

    def system_prompt_fragment(self) -> str:
        return (
            "You are controlling a deterministic sqlite3 CLI environment.\n"
            "Rules:\n"
            "- Use run_sqlite for SQL execution.\n"
            "- You must read at least one routed skill with read_skill before run_sqlite.\n"
            "- Use read_skill whenever routed skill summaries are insufficient for exact execution.\n"
            "- Use show_fixture to inspect fixture/bootstrap files.\n"
            "- Keep SQL concise, deterministic, and verifiable.\n"
            "- Do not use unsupported sqlite shell actions.\n"
        )

    def quality_keywords(self) -> re.Pattern[str]:
        return _SQL_KEYWORDS

    def build_alias_map(self, *, opaque: bool) -> dict[str, str]:
        result: dict[str, str] = {}
        for canonical, alias in _SQLITE_ALIASES.items():
            api_name = alias.opaque_name if opaque else canonical
            result[api_name] = canonical
        return result
