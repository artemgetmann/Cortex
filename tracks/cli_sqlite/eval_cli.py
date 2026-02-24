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


def unresolved_contract_gaps(evaluation: CliEvaluation | dict[str, Any]) -> list[dict[str, Any]]:
    """
    Convert deterministic evaluation output into normalized unresolved-gap rows.

    These rows are designed for two in-loop uses:
    - targeted pre-stop retry prompts
    - structured lesson metadata (reason_code/gap_type/gap_signature)
    """
    payload = evaluation.to_dict() if isinstance(evaluation, CliEvaluation) else dict(evaluation or {})
    evidence = payload.get("evidence", {})
    if not isinstance(evidence, dict):
        evidence = {}
    gaps: list[dict[str, Any]] = []

    required_missing = evidence.get("required_patterns", {}).get("missing", [])
    if isinstance(required_missing, list):
        for pattern in required_missing:
            text = str(pattern).strip()
            if not text:
                continue
            gaps.append(
                {
                    "reason_code": "missing_required_pattern",
                    "gap_type": "required_sql_pattern",
                    "detail": text,
                    "gap_signature": f"missing_required_pattern|required_sql_pattern|{text}",
                }
            )

    forbidden_matched = evidence.get("forbidden_patterns", {}).get("matched", [])
    if isinstance(forbidden_matched, list):
        for pattern in forbidden_matched:
            text = str(pattern).strip()
            if not text:
                continue
            gaps.append(
                {
                    "reason_code": "matched_forbidden_pattern",
                    "gap_type": "forbidden_sql_pattern",
                    "detail": text,
                    "gap_signature": f"matched_forbidden_pattern|forbidden_sql_pattern|{text}",
                }
            )

    required_event_missing = evidence.get("required_event_patterns", {}).get("missing", [])
    if isinstance(required_event_missing, list):
        for pattern in required_event_missing:
            text = str(pattern).strip()
            if not text:
                continue
            gaps.append(
                {
                    "reason_code": "missing_required_event_pattern",
                    "gap_type": "required_event_pattern",
                    "detail": text,
                    "gap_signature": f"missing_required_event_pattern|required_event_pattern|{text}",
                }
            )

    forbidden_event_matched = evidence.get("forbidden_event_patterns", {}).get("matched", [])
    if isinstance(forbidden_event_matched, list):
        for pattern in forbidden_event_matched:
            text = str(pattern).strip()
            if not text:
                continue
            gaps.append(
                {
                    "reason_code": "matched_forbidden_event_pattern",
                    "gap_type": "forbidden_event_pattern",
                    "detail": text,
                    "gap_signature": f"matched_forbidden_event_pattern|forbidden_event_pattern|{text}",
                }
            )

    required_files_missing = evidence.get("required_files", {}).get("missing", [])
    if isinstance(required_files_missing, list):
        for rel_path in required_files_missing:
            text = str(rel_path).strip()
            if not text:
                continue
            gaps.append(
                {
                    "reason_code": "missing_required_file",
                    "gap_type": "required_file",
                    "detail": text,
                    "gap_signature": f"missing_required_file|required_file|{text}",
                }
            )

    required_file_content_missing = evidence.get("required_file_content_patterns", {}).get("missing", [])
    if isinstance(required_file_content_missing, list):
        for row in required_file_content_missing:
            if not isinstance(row, dict):
                continue
            rel_path = str(row.get("path", "")).strip()
            pattern = str(row.get("pattern", "")).strip()
            if not rel_path or not pattern:
                continue
            detail = f"{rel_path}::{pattern}"
            gaps.append(
                {
                    "reason_code": "missing_required_file_content_pattern",
                    "gap_type": "required_file_content_pattern",
                    "detail": detail,
                    "gap_signature": f"missing_required_file_content_pattern|required_file_content_pattern|{detail}",
                }
            )

    required_queries = evidence.get("required_queries", [])
    if isinstance(required_queries, list):
        for query in required_queries:
            if not isinstance(query, dict):
                continue
            if bool(query.get("matched", False)):
                continue
            query_id = str(query.get("id", "required_query")).strip() or "required_query"
            query_error = str(query.get("error", "")).strip()
            detail = query_id if not query_error else f"{query_id}: {query_error}"
            gaps.append(
                {
                    "reason_code": "required_query_mismatch",
                    "gap_type": "required_query",
                    "detail": detail,
                    "gap_signature": f"required_query_mismatch|required_query|{query_id}",
                }
            )

    error_count = int(evidence.get("error_count", 0) or 0)
    max_error_count = int(evidence.get("max_error_count", 0) or 0)
    if error_count > max_error_count:
        detail = f"error_count={error_count} max_error_count={max_error_count}"
        gaps.append(
            {
                "reason_code": "too_many_errors",
                "gap_type": "error_budget",
                "detail": detail,
                "gap_signature": f"too_many_errors|error_budget|{detail}",
            }
        )

    # Keep order deterministic while removing accidental duplicates.
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in gaps:
        signature = str(row.get("gap_signature", "")).strip()
        if not signature or signature in seen:
            continue
        seen.add(signature)
        deduped.append(row)
    return deduped


DEFAULT_CONTRACT = {
    "id": "cli-sqlite-import-aggregate-v1",
    "task_match": {"all": ["sqlite"], "any": ["import", "aggregate", "group"]},
    "setup": {"bootstrap_sql_path": "bootstrap.sql", "fixture_paths": ["fixture.csv"]},
    "signals": {
        "required_sql_patterns": [
            "(?is)create\\s+table(?:\\s+if\\s+not\\s+exists)?\\s+sales",
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


def _build_event_text(events: list[dict[str, Any]]) -> str:
    """Flatten tool events into deterministic text for pattern checks."""
    lines: list[str] = []
    for row in events:
        if not isinstance(row, dict):
            continue
        tool = str(row.get("tool", ""))
        tool_input = row.get("tool_input")
        output = row.get("output")
        error = row.get("error")
        try:
            input_text = json.dumps(tool_input, sort_keys=True, ensure_ascii=True)
        except Exception:
            input_text = str(tool_input)
        lines.append(
            f"tool={tool} input={input_text} output={str(output)} error={str(error)}"
        )
    return "\n".join(lines)


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
    required_event_patterns = [str(p) for p in signals.get("required_event_patterns", []) if str(p).strip()]
    forbidden_event_patterns = [str(p) for p in signals.get("forbidden_event_patterns", []) if str(p).strip()]
    required_files = [str(p) for p in signals.get("required_files", []) if str(p).strip()]
    required_file_content_patterns_raw = signals.get("required_file_content_patterns", [])
    required_file_content_patterns: list[dict[str, Any]] = []
    if isinstance(required_file_content_patterns_raw, list):
        for item in required_file_content_patterns_raw:
            if not isinstance(item, dict):
                continue
            rel_path = str(item.get("path", "")).strip()
            raw_patterns = item.get("patterns", [])
            if not rel_path or not isinstance(raw_patterns, list):
                continue
            patterns = [str(pattern).strip() for pattern in raw_patterns if str(pattern).strip()]
            if not patterns:
                continue
            required_file_content_patterns.append({"path": rel_path, "patterns": patterns})
    required_queries = signals.get("required_queries", [])
    if not isinstance(required_queries, list):
        required_queries = []
    max_error_count = int(signals.get("max_error_count", 0))

    sql_runs, error_count = _collect_sql_events(events)
    merged_sql = "\n\n".join(sql_runs)
    merged_events = _build_event_text(events)
    work_dir = db_path.parent

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

    matched_required_event_patterns: list[str] = []
    missing_required_event_patterns: list[str] = []
    for pattern in required_event_patterns:
        if re.search(pattern, merged_events, flags=0):
            matched_required_event_patterns.append(pattern)
        else:
            missing_required_event_patterns.append(pattern)

    matched_forbidden_event_patterns: list[str] = []
    for pattern in forbidden_event_patterns:
        if re.search(pattern, merged_events, flags=0):
            matched_forbidden_event_patterns.append(pattern)

    missing_required_files: list[str] = []
    for rel_path in required_files:
        if not (work_dir / rel_path).exists():
            missing_required_files.append(rel_path)

    matched_required_file_content_patterns: list[dict[str, str]] = []
    missing_required_file_content_patterns: list[dict[str, str]] = []
    for row in required_file_content_patterns:
        rel_path = str(row.get("path", "")).strip()
        patterns = row.get("patterns", [])
        if not rel_path or not isinstance(patterns, list):
            continue
        target_path = work_dir / rel_path
        file_text = ""
        if target_path.exists():
            try:
                file_text = target_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                file_text = ""
        # Every required pattern is checked independently so failures are
        # explicit in the gap report and directly usable for lesson routing.
        for pattern in patterns:
            pattern_text = str(pattern).strip()
            if not pattern_text:
                continue
            if file_text and re.search(pattern_text, file_text, flags=0):
                matched_required_file_content_patterns.append(
                    {"path": rel_path, "pattern": pattern_text}
                )
            else:
                missing_required_file_content_patterns.append(
                    {"path": rel_path, "pattern": pattern_text}
                )

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

    checks_total = (
        len(required_patterns)
        + len(forbidden_patterns)
        + len(required_event_patterns)
        + len(forbidden_event_patterns)
        + len(required_files)
        + sum(len(row.get("patterns", [])) for row in required_file_content_patterns)
        + len(query_results)
        + 1
    )
    checks_passed = (
        len(matched_required)
        + (len(forbidden_patterns) - len(matched_forbidden))
        + len(matched_required_event_patterns)
        + (len(forbidden_event_patterns) - len(matched_forbidden_event_patterns))
        + (len(required_files) - len(missing_required_files))
        + len(matched_required_file_content_patterns)
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
    if missing_required_event_patterns:
        reasons.append("missing_required_event_pattern")
    if matched_forbidden_event_patterns:
        reasons.append("matched_forbidden_event_pattern")
    if missing_required_files:
        reasons.append("missing_required_file")
    if missing_required_file_content_patterns:
        reasons.append("missing_required_file_content_pattern")
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
        "required_event_patterns": {
            "matched": matched_required_event_patterns,
            "missing": missing_required_event_patterns,
        },
        "forbidden_event_patterns": {"matched": matched_forbidden_event_patterns},
        "required_files": {"missing": missing_required_files, "work_dir": str(work_dir)},
        "required_file_content_patterns": {
            "matched": matched_required_file_content_patterns,
            "missing": missing_required_file_content_patterns,
        },
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
