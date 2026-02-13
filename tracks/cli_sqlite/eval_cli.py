from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CliEvaluation:
    applicable: bool
    passed: bool
    score: float
    reasons: list[str]
    evidence: dict[str, Any]
    contract_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "applicable": self.applicable,
            "passed": self.passed,
            "score": self.score,
            "reasons": self.reasons,
            "evidence": self.evidence,
            "contract_path": self.contract_path,
        }


DEFAULT_CONTRACT = {
    "id": "cli-sqlite-import-aggregate-v1",
    "task_match": {"all": ["sqlite"], "any": ["import", "aggregate", "group"]},
    "setup": {"bootstrap_sql_path": "bootstrap.sql", "fixture_paths": ["fixture.csv"]},
    "signals": {
        "required_sql_patterns": [
            "(?is)create\\s+table\\s+sales",
            "(?is)insert\\s+into\\s+sales",
            "(?is)group\\s+by\\s+category",
            "(?is)order\\s+by\\s+category",
        ],
        "forbidden_sql_patterns": ["(?is)drop\\s+table\\s+sales"],
        "required_queries": [
            {
                "id": "aggregate_rows",
                "sql": "SELECT category, SUM(amount) AS total FROM sales GROUP BY category ORDER BY category;",
                "expected_rows": [["bass", "9"], ["drums", "13"], ["lead", "8"]],
            }
        ],
        "max_error_count": 1,
    },
    "pass_rule": "all_required && no_forbidden && required_queries_match && errors_within_budget",
    "reason_codes": [
        "missing_required_pattern",
        "matched_forbidden_pattern",
        "required_query_mismatch",
        "too_many_errors",
    ],
}


def load_contract(tasks_root: Path, task_id: str) -> tuple[dict[str, Any], Path]:
    path = tasks_root / task_id / "CONTRACT.json"
    if not path.exists():
        return dict(DEFAULT_CONTRACT), path
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULT_CONTRACT), path
    if not isinstance(data, dict):
        return dict(DEFAULT_CONTRACT), path
    return data, path


def _task_matches(task: str, contract: dict[str, Any]) -> bool:
    task_match = contract.get("task_match", {})
    if not isinstance(task_match, dict):
        return False
    lowered = task.lower()
    all_terms = [str(item).lower() for item in task_match.get("all", []) if str(item).strip()]
    any_terms = [str(item).lower() for item in task_match.get("any", []) if str(item).strip()]
    if all_terms and not all(term in lowered for term in all_terms):
        return False
    if any_terms and not any(term in lowered for term in any_terms):
        return False
    return True


def _collect_sql_events(events: list[dict[str, Any]]) -> tuple[list[str], int]:
    sql_runs: list[str] = []
    error_count = 0
    for event in events:
        if event.get("tool") != "run_sqlite":
            continue
        tool_input = event.get("tool_input", {})
        if isinstance(tool_input, dict):
            sql = tool_input.get("sql")
            if isinstance(sql, str):
                sql_runs.append(sql)
        if not bool(event.get("ok", False)):
            error_count += 1
    return sql_runs, error_count


def _query_rows(db_path: Path, sql: str) -> tuple[list[list[str]] | None, str | None]:
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.execute(sql)
            rows = cursor.fetchall()
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
    normalized: list[list[str]] = []
    for row in rows:
        normalized.append([str(col) for col in row])
    return normalized, None


def evaluate_cli_session(
    *,
    task: str,
    task_id: str,
    events: list[dict[str, Any]],
    db_path: Path,
    tasks_root: Path,
) -> CliEvaluation:
    contract, contract_path = load_contract(tasks_root, task_id)
    if not _task_matches(task, contract):
        return CliEvaluation(
            applicable=False,
            passed=False,
            score=0.0,
            reasons=[],
            evidence={"note": "task did not match contract task_match"},
            contract_path=str(contract_path),
        )

    signals = contract.get("signals", {}) if isinstance(contract.get("signals"), dict) else {}
    required_patterns = [str(p) for p in signals.get("required_sql_patterns", []) if str(p).strip()]
    forbidden_patterns = [str(p) for p in signals.get("forbidden_sql_patterns", []) if str(p).strip()]
    required_queries = signals.get("required_queries", [])
    if not isinstance(required_queries, list):
        required_queries = []
    max_error_count = int(signals.get("max_error_count", 0))

    sql_runs, error_count = _collect_sql_events(events)
    merged_sql = "\n\n".join(sql_runs)

    matched_required: list[str] = []
    missing_required: list[str] = []
    for pattern in required_patterns:
        if re.search(pattern, merged_sql, flags=0):
            matched_required.append(pattern)
        else:
            missing_required.append(pattern)

    matched_forbidden: list[str] = []
    for pattern in forbidden_patterns:
        if re.search(pattern, merged_sql, flags=0):
            matched_forbidden.append(pattern)

    query_results: list[dict[str, Any]] = []
    query_failures = 0
    for query_spec in required_queries:
        if not isinstance(query_spec, dict):
            continue
        query_id = str(query_spec.get("id", "required_query"))
        query_sql = str(query_spec.get("sql", "")).strip()
        expected_rows = query_spec.get("expected_rows", [])
        if not isinstance(expected_rows, list):
            expected_rows = []

        actual_rows, query_error = _query_rows(db_path, query_sql)
        normalized_expected = [
            [str(col) for col in row]
            for row in expected_rows
            if isinstance(row, list)
        ]
        matched = query_error is None and actual_rows == normalized_expected
        if not matched:
            query_failures += 1
        query_results.append(
            {
                "id": query_id,
                "sql": query_sql,
                "matched": matched,
                "error": query_error,
                "expected_rows": normalized_expected,
                "actual_rows": actual_rows,
            }
        )

    checks_total = len(required_patterns) + len(forbidden_patterns) + len(query_results) + 1
    checks_passed = (
        len(matched_required)
        + (len(forbidden_patterns) - len(matched_forbidden))
        + (len(query_results) - query_failures)
        + (1 if error_count <= max_error_count else 0)
    )
    score = 0.0 if checks_total <= 0 else round(max(0.0, checks_passed / float(checks_total)), 3)

    reasons: list[str] = []
    if missing_required:
        reasons.append("missing_required_pattern")
    if matched_forbidden:
        reasons.append("matched_forbidden_pattern")
    if query_failures > 0:
        reasons.append("required_query_mismatch")
    if error_count > max_error_count:
        reasons.append("too_many_errors")
    reasons = sorted(set(reasons))
    passed = len(reasons) == 0

    evidence = {
        "sql_event_count": len(sql_runs),
        "error_count": error_count,
        "max_error_count": max_error_count,
        "required_patterns": {"matched": matched_required, "missing": missing_required},
        "forbidden_patterns": {"matched": matched_forbidden},
        "required_queries": query_results,
    }
    return CliEvaluation(
        applicable=True,
        passed=passed,
        score=(1.0 if passed else score),
        reasons=reasons,
        evidence=evidence,
        contract_path=str(contract_path),
    )
