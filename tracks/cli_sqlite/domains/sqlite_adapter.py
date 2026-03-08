"""SQLite domain adapter — wraps existing executor.py into the DomainAdapter protocol."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from tracks.cli_sqlite.domain_adapter import DomainAdapter, DomainDoc, DomainWorkspace, ToolResult
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
SQLITE_DOCS_DIR = Path(__file__).resolve().parent / "docs"

# Re-use the existing SQL keywords regex from learning_cli.py
_SQL_KEYWORDS = re.compile(
    r"(?i)\b("
    r"SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|BEGIN|COMMIT|ROLLBACK|"
    r"ON CONFLICT|GROUP BY|ORDER BY|WHERE|JOIN|PRIMARY KEY|FOREIGN KEY|"
    r"INTEGER|TEXT|REAL|BLOB|NULL|NOT NULL|UNIQUE|INDEX|TRANSACTION|"
    r"SUM|COUNT|AVG|MAX|MIN|HAVING|DISTINCT|UNION|EXCEPT|INTERSECT|"
    r"VALUES|INTO|FROM|TABLE|VIEW|TRIGGER|"
    r"fixture_seed|ledger|rejects|checkpoint_log|batch_audit|sales|error_log|inventory"
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


def _sqlite_gap_fix_recipe(gap: dict[str, Any]) -> str:
    """Build one sqlite-specific deterministic repair recipe from one gap row.

    Intent:
    - Keep this domain logic in the adapter, not in the core orchestrator.
    - Return command-oriented hints that weaker models can execute directly.
    """
    reason = str(gap.get("reason_code", "")).strip()
    detail = str(gap.get("detail", "")).strip()
    query_id = str(gap.get("query_id", "")).strip()
    query_sql = str(gap.get("query_sql", "")).strip()
    expected_rows = gap.get("expected_rows", [])
    expected_suffix = (
        f" expected_rows={json.dumps(expected_rows, ensure_ascii=True)}"
        if isinstance(expected_rows, list)
        else ""
    )

    if reason == "required_query_mismatch" and query_id in {"reject_count", "reject_breakdown"}:
        return (
            "Deterministic sqlite recipe (reject_count): run_sqlite(sql=\"PRAGMA table_info(rejects);\") "
            "then run_sqlite(sql=\""
            "INSERT INTO rejects(event_id, reason) "
            "SELECT fs.event_id, 'duplicate_event' "
            "FROM fixture_seed fs "
            "JOIN (SELECT event_id FROM fixture_seed GROUP BY event_id HAVING COUNT(*) > 1) dup "
            "ON dup.event_id = fs.event_id "
            "WHERE NOT EXISTS ("
            "SELECT 1 FROM rejects r WHERE r.event_id = fs.event_id AND r.reason = 'duplicate_event'"
            ");\"). "
            f"Then run validator query exactly: {query_sql}{expected_suffix}"
        )
    if reason == "required_query_mismatch" and query_id == "batch_audit_row":
        return (
            "Deterministic sqlite recipe (batch_audit): run_sqlite(sql=\""
            "INSERT OR REPLACE INTO batch_audit(batch_tag, accepted_count, rejected_count) "
            "SELECT 'BATCH-MAY-01', (SELECT COUNT(*) FROM ledger), (SELECT COUNT(*) FROM rejects);"
            "\"). "
            f"Then run validator query exactly: {query_sql}{expected_suffix}"
        )
    if reason == "required_query_mismatch" and query_id in {"ledger_aggregate", "ledger_count"}:
        return (
            "Deterministic sqlite recipe (ledger): run_sqlite(sql=\""
            "INSERT INTO ledger(event_id, category, amount, batch_id) "
            "SELECT fs.event_id, fs.category, fs.amount, fs.batch_id "
            "FROM fixture_seed fs "
            "WHERE NOT EXISTS (SELECT 1 FROM ledger l WHERE l.event_id = fs.event_id);"
            "\"). "
            f"Then run validator query exactly: {query_sql}{expected_suffix}"
        )
    if reason == "missing_required_pattern" and "insert\\s+into\\s+ledger" in detail.lower():
        return (
            "Deterministic sqlite recipe: use explicit ledger insert shape "
            "run_sqlite(sql=\"INSERT INTO ledger(event_id, category, amount, batch_id) "
            "SELECT fs.event_id, fs.category, fs.amount, fs.batch_id "
            "FROM fixture_seed fs "
            "WHERE NOT EXISTS (SELECT 1 FROM ledger l WHERE l.event_id = fs.event_id);\")."
        )
    if reason == "missing_required_pattern" and "insert\\s+into\\s+rejects" in detail.lower():
        return (
            "Deterministic sqlite recipe: use rejects schema-safe insert "
            "run_sqlite(sql=\"INSERT INTO rejects(event_id, reason) "
            "SELECT fs.event_id, 'duplicate_event' "
            "FROM fixture_seed fs "
            "JOIN (SELECT event_id FROM fixture_seed GROUP BY event_id HAVING COUNT(*) > 1) dup "
            "ON dup.event_id = fs.event_id "
            "WHERE NOT EXISTS ("
            "SELECT 1 FROM rejects r WHERE r.event_id = fs.event_id AND r.reason = 'duplicate_event'"
            ");\")."
        )
    if reason == "too_many_errors":
        return (
            "Deterministic sqlite recipe (error budget): first run schema probe "
            "run_sqlite(sql=\"PRAGMA table_info(ledger); PRAGMA table_info(rejects);\") "
            "then execute one mutating SQL block only, then validator SELECT queries."
        )
    if reason == "matched_forbidden_pattern":
        return (
            "Deterministic sqlite recipe: avoid forbidden SQL patterns entirely. "
            "Use INSERT/UPDATE/SELECT only and verify required queries before stop."
        )

    # Adapter fallback is intentionally lightweight; core orchestrator still has
    # generic reason_code/gap_type fallback logic for any domain.
    if query_sql:
        return f"Run validator query and reconcile data exactly: {query_sql}{expected_suffix}"
    if detail:
        return f"Resolve sqlite gap by fixing: {detail}"
    return "Resolve sqlite contract gap before stopping."


def _sqlite_incremental_forced_repair_recipe(*, task_id: str, gap: dict[str, Any]) -> str:
    """Return a strict, executable repair recipe for incremental reconcile tasks.

    Why this helper exists:
    - Weak models tend to stop after generic advice when required query checks fail.
    - This function emits one deterministic three-step sequence (repair -> verify -> stop-on-mismatch)
      so closure behavior is explicit and auditable.
    """
    reason = str(gap.get("reason_code", "")).strip()
    if reason not in {"required_query_mismatch", "missing_required_pattern", "too_many_errors"}:
        return ""
    task_key = str(task_id).strip().lower()
    if not task_key.startswith("incremental_reconcile"):
        return ""
    query_sql = str(gap.get("query_sql", "")).strip()
    query_id = str(gap.get("query_id", "")).strip()
    expected_rows = gap.get("expected_rows", [])
    if reason == "required_query_mismatch" and not query_sql:
        return ""

    # Task-specific repair SQL intentionally targets known fixture/schema for
    # incremental reconcile tasks while staying deterministic and idempotent.
    if task_key == "incremental_reconcile":
        repair_sql = (
            "BEGIN IMMEDIATE; "
            "INSERT INTO ledger(event_id, category, amount, batch_id, checkpoint_tag) "
            "SELECT fs.event_id, fs.category, fs.amount, fs.batch_id, 'CKP-APR-01' "
            "FROM fixture_seed fs "
            "WHERE fs.rowid = (SELECT MIN(f2.rowid) FROM fixture_seed f2 WHERE f2.event_id = fs.event_id) "
            "AND NOT EXISTS (SELECT 1 FROM ledger l WHERE l.event_id = fs.event_id); "
            "INSERT INTO rejects(event_id, reason) "
            "SELECT dup.event_id, 'duplicate_event' "
            "FROM (SELECT event_id FROM fixture_seed GROUP BY event_id HAVING COUNT(*) > 1) dup "
            "WHERE NOT EXISTS (SELECT 1 FROM rejects r WHERE r.event_id = dup.event_id AND r.reason = 'duplicate_event'); "
            "INSERT OR REPLACE INTO checkpoint_log(checkpoint_tag, row_count) "
            "SELECT 'CKP-APR-01', COUNT(*) FROM ledger WHERE checkpoint_tag = 'CKP-APR-01'; "
            "COMMIT;"
        )
    elif task_key == "incremental_reconcile_audit_transfer":
        repair_sql = (
            "BEGIN IMMEDIATE; "
            "INSERT INTO ledger(event_id, category, amount, batch_id) "
            "SELECT fs.event_id, fs.category, CAST(fs.amount AS INTEGER), fs.batch_id "
            "FROM fixture_seed fs "
            "WHERE ((trim(fs.amount) GLOB '[0-9]*') OR (trim(fs.amount) GLOB '-[0-9]*')) "
            "AND trim(fs.amount) NOT IN ('', '-') "
            "AND fs.rowid = (SELECT MIN(f2.rowid) FROM fixture_seed f2 WHERE f2.event_id = fs.event_id) "
            "AND NOT EXISTS (SELECT 1 FROM ledger l WHERE l.event_id = fs.event_id); "
            "INSERT INTO rejects(event_id, reason) "
            "SELECT fs.event_id, "
            "CASE "
            "WHEN NOT (((trim(fs.amount) GLOB '[0-9]*') OR (trim(fs.amount) GLOB '-[0-9]*')) AND trim(fs.amount) NOT IN ('', '-')) THEN 'invalid_amount' "
            "ELSE 'duplicate_event' "
            "END "
            "FROM fixture_seed fs "
            "WHERE ("
            "NOT (((trim(fs.amount) GLOB '[0-9]*') OR (trim(fs.amount) GLOB '-[0-9]*')) AND trim(fs.amount) NOT IN ('', '-'))"
            "OR fs.rowid != (SELECT MIN(f2.rowid) FROM fixture_seed f2 WHERE f2.event_id = fs.event_id)) "
            "AND NOT EXISTS (SELECT 1 FROM rejects r WHERE r.event_id = fs.event_id); "
            "INSERT OR REPLACE INTO batch_audit(batch_tag, accepted_count, rejected_count) "
            "SELECT 'BATCH-MAY-01', (SELECT COUNT(*) FROM ledger), (SELECT COUNT(*) FROM rejects); "
            "COMMIT;"
        )
    elif task_key == "incremental_reconcile_replay_safe":
        repair_sql = (
            "BEGIN IMMEDIATE; "
            "INSERT INTO ledger(event_id, category, amount, batch_id) "
            "SELECT fs.event_id, fs.category, CAST(fs.amount AS INTEGER), fs.batch_id "
            "FROM fixture_seed fs "
            "WHERE ((trim(fs.amount) GLOB '[0-9]*') OR (trim(fs.amount) GLOB '-[0-9]*')) "
            "AND trim(fs.amount) NOT IN ('', '-') "
            "AND fs.rowid = (SELECT MIN(f2.rowid) FROM fixture_seed f2 WHERE f2.event_id = fs.event_id) "
            "AND NOT EXISTS (SELECT 1 FROM ledger l WHERE l.event_id = fs.event_id); "
            "INSERT INTO rejects(event_id, reason, batch_id) "
            "SELECT fs.event_id, "
            "CASE "
            "WHEN NOT (((trim(fs.amount) GLOB '[0-9]*') OR (trim(fs.amount) GLOB '-[0-9]*')) AND trim(fs.amount) NOT IN ('', '-')) THEN 'invalid_amount' "
            "ELSE 'duplicate_event' "
            "END, "
            "'BATCH-REPLAY-01' "
            "FROM fixture_seed fs "
            "WHERE ("
            "NOT (((trim(fs.amount) GLOB '[0-9]*') OR (trim(fs.amount) GLOB '-[0-9]*')) AND trim(fs.amount) NOT IN ('', '-')) "
            "OR fs.rowid != (SELECT MIN(f2.rowid) FROM fixture_seed f2 WHERE f2.event_id = fs.event_id)) "
            "AND NOT EXISTS ("
            "SELECT 1 FROM rejects r "
            "WHERE r.event_id = fs.event_id "
            "AND r.reason = CASE "
            "WHEN NOT (((trim(fs.amount) GLOB '[0-9]*') OR (trim(fs.amount) GLOB '-[0-9]*')) AND trim(fs.amount) NOT IN ('', '-')) THEN 'invalid_amount' "
            "ELSE 'duplicate_event' "
            "END "
            "AND r.batch_id = 'BATCH-REPLAY-01'"
            "); "
            "INSERT OR IGNORE INTO replay_log(batch_tag, replay_step) VALUES ('BATCH-REPLAY-01', 1); "
            "INSERT OR IGNORE INTO replay_log(batch_tag, replay_step) VALUES ('BATCH-REPLAY-01', 2); "
            "INSERT OR REPLACE INTO batch_audit(batch_tag, accepted_count, rejected_count, replay_count) "
            "VALUES ("
            "'BATCH-REPLAY-01', "
            "(SELECT COUNT(*) FROM ledger WHERE batch_id = 'b9'), "
            "(SELECT COUNT(*) FROM rejects WHERE batch_id = 'BATCH-REPLAY-01'), "
            "(SELECT COUNT(*) FROM replay_log WHERE batch_tag = 'BATCH-REPLAY-01')"
            "); "
            "COMMIT;"
        )
    else:
        # nano variant has no checkpoint table/column, so use the lean path.
        repair_sql = (
            "BEGIN IMMEDIATE; "
            "INSERT INTO ledger(event_id, category, amount, batch_id) "
            "SELECT fs.event_id, fs.category, fs.amount, fs.batch_id "
            "FROM fixture_seed fs "
            "WHERE fs.rowid = (SELECT MIN(f2.rowid) FROM fixture_seed f2 WHERE f2.event_id = fs.event_id) "
            "AND NOT EXISTS (SELECT 1 FROM ledger l WHERE l.event_id = fs.event_id); "
            "INSERT INTO rejects(event_id, reason) "
            "SELECT dup.event_id, 'duplicate_event' "
            "FROM (SELECT event_id FROM fixture_seed GROUP BY event_id HAVING COUNT(*) > 1) dup "
            "WHERE NOT EXISTS (SELECT 1 FROM rejects r WHERE r.event_id = dup.event_id AND r.reason = 'duplicate_event'); "
            "COMMIT;"
        )

    if reason == "required_query_mismatch":
        expected_suffix = (
            f" expected_rows={json.dumps(expected_rows, ensure_ascii=True)}"
            if isinstance(expected_rows, list)
            else ""
        )
        return (
            "[forced_repair sqlite_incremental_required_query_mismatch_v1] "
            f"query_id={query_id or 'required_query'} "
            f"step1=run_sqlite(sql={json.dumps(repair_sql, ensure_ascii=True)}) "
            f"step2=run_sqlite(sql={json.dumps(query_sql, ensure_ascii=True)})"
            f"{expected_suffix} "
            "step3=if_mismatch_stop_and_report"
        )

    # Missing-pattern and error-budget gaps get the same deterministic closure
    # transaction so the model can satisfy all required SQL signals in one shot.
    return (
        "[forced_repair sqlite_incremental_closure_v1] "
        f"step1=run_sqlite(sql={json.dumps(repair_sql, ensure_ascii=True)}) "
        "step2=run_sqlite(sql=\"SELECT COUNT(*) FROM ledger; SELECT COUNT(*) FROM rejects;\") "
        "step3=if_errors_stop_and_report"
    )


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

    def docs_manifest(self) -> list[DomainDoc]:
        docs = [
            DomainDoc(
                doc_id="sqlite/reference",
                path=SQLITE_DOCS_DIR / "sqlite-reference.md",
                title="SQLite Reference",
                tags=("sqlite", "sql", "query", "aggregate", "transaction"),
            )
        ]
        return [doc for doc in docs if doc.path.exists()]

    def deterministic_gap_recipes(
        self,
        *,
        task_id: str,
        unresolved_gaps: list[dict[str, Any]],
        max_items: int = 3,
    ) -> list[str]:
        """Optional adapter hook: domain-specific deterministic gap recipes.

        This method is consumed via dynamic lookup by the orchestrator so other
        domains can ignore it. We keep it side-effect free and deterministic.
        """
        recipes: list[str] = []
        dedup: set[str] = set()
        reason_priority = {
            "required_query_mismatch": 0,
            "missing_required_pattern": 1,
            "too_many_errors": 2,
            "matched_forbidden_pattern": 3,
        }
        sorted_rows = sorted(
            [row for row in unresolved_gaps if isinstance(row, dict)],
            key=lambda row: (
                int(reason_priority.get(str(row.get("reason_code", "")).strip(), 9)),
                str(row.get("gap_type", "")).strip(),
                str(row.get("detail", "")).strip(),
            ),
        )
        for row in sorted_rows:
            if not isinstance(row, dict):
                continue
            # Forced recipe takes precedence for incremental reconcile mismatch
            # closure because it materially improves weak-model reliability.
            forced_recipe = _sqlite_incremental_forced_repair_recipe(task_id=task_id, gap=row)
            # For incremental reconcile tasks we only want executable SQL-shaped
            # recipes; generic regex prose degrades weak-model behavior.
            if forced_recipe:
                recipe = forced_recipe
            elif str(task_id).strip().lower().startswith("incremental_reconcile"):
                continue
            else:
                recipe = _sqlite_gap_fix_recipe(row)
            text = " ".join(str(recipe).split()).strip()
            if not text:
                continue
            key = text.lower()
            if key in dedup:
                continue
            dedup.add(key)
            recipes.append(text)
            if len(recipes) >= max(1, int(max_items)):
                break
        return recipes
