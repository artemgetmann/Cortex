from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tracks.cli_sqlite.domain_adapter import DomainWorkspace
from tracks.cli_sqlite import verification_runtime_helpers as _verification_runtime_helpers


@dataclass(frozen=True)
class VerificationFilePattern:
    """Deterministic file-content probe declared in VERIFICATION.json."""

    path: str
    pattern: str


@dataclass(frozen=True)
class VerificationQueryCheck:
    """Deterministic sqlite query probe declared in VERIFICATION.json."""

    id: str
    sql: str
    expected_rows: tuple[tuple[str, ...], ...]
    db_path: str = "task.db"


@dataclass(frozen=True)
class VerificationSpec:
    """Task-local deterministic probes for no-contract domains."""

    source: str
    exact_output_lines: tuple[str, ...] = ()
    required_files: tuple[str, ...] = ()
    file_content_patterns: tuple[VerificationFilePattern, ...] = ()
    query_checks: tuple[VerificationQueryCheck, ...] = ()

    def check_count(self) -> int:
        return (
            len(self.exact_output_lines)
            + len(self.required_files)
            + len(self.file_content_patterns)
            + len(self.query_checks)
        )


@dataclass(frozen=True)
class DeterministicProbeResult:
    """Unified probe result shape used for metrics + eval decisions."""

    source: str
    applicable: bool
    passed: bool
    score: float
    reasons: list[str]
    evidence: dict[str, Any]

    def to_eval_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "applicable": self.applicable,
            "passed": self.passed,
            "score": self.score,
            "reasons": list(self.reasons),
            "evidence": dict(self.evidence),
        }


def _parse_expected_rows(raw_rows: Any, *, field_name: str, errors: list[str]) -> tuple[tuple[str, ...], ...]:
    if not isinstance(raw_rows, list):
        errors.append(f"{field_name}_must_be_list")
        return ()
    normalized: list[tuple[str, ...]] = []
    for row_idx, row in enumerate(raw_rows):
        if not isinstance(row, list):
            errors.append(f"{field_name}[{row_idx}]_must_be_list")
            continue
        normalized.append(tuple(str(col) for col in row))
    return tuple(normalized)


def _load_verification_spec_from_json(path: Path) -> tuple[VerificationSpec | None, list[str]]:
    """Load and schema-check VERIFICATION.json for deterministic no-contract probes."""
    errors: list[str] = []
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, [f"invalid_json:{type(exc).__name__}"]
    if not isinstance(parsed, dict):
        return None, ["root_must_be_object"]

    def read_str_list(key: str) -> tuple[str, ...]:
        raw = parsed.get(key, [])
        if raw is None:
            return ()
        if not isinstance(raw, list):
            errors.append(f"{key}_must_be_list")
            return ()
        values: list[str] = []
        for idx, item in enumerate(raw):
            text = str(item).strip() if isinstance(item, str) else ""
            if not text:
                errors.append(f"{key}[{idx}]_must_be_non_empty_string")
                continue
            values.append(text)
        return tuple(values)

    exact_output_lines = read_str_list("exact_output_lines")
    required_files = read_str_list("required_files")

    raw_patterns = parsed.get("file_content_patterns", [])
    file_content_patterns: list[VerificationFilePattern] = []
    if raw_patterns is not None:
        if not isinstance(raw_patterns, list):
            errors.append("file_content_patterns_must_be_list")
        else:
            for idx, row in enumerate(raw_patterns):
                if not isinstance(row, dict):
                    errors.append(f"file_content_patterns[{idx}]_must_be_object")
                    continue
                path_value = str(row.get("path", "")).strip()
                pattern_value = str(row.get("pattern", "")).strip()
                if not path_value:
                    errors.append(f"file_content_patterns[{idx}].path_required")
                    continue
                if not pattern_value:
                    errors.append(f"file_content_patterns[{idx}].pattern_required")
                    continue
                file_content_patterns.append(
                    VerificationFilePattern(path=path_value, pattern=pattern_value)
                )

    raw_queries = parsed.get("query_checks", [])
    query_checks: list[VerificationQueryCheck] = []
    if raw_queries is not None:
        if not isinstance(raw_queries, list):
            errors.append("query_checks_must_be_list")
        else:
            for idx, row in enumerate(raw_queries):
                if not isinstance(row, dict):
                    errors.append(f"query_checks[{idx}]_must_be_object")
                    continue
                query_sql = str(row.get("sql", "")).strip()
                if not query_sql:
                    errors.append(f"query_checks[{idx}].sql_required")
                    continue
                query_id = str(row.get("id", f"query_{idx}")).strip() or f"query_{idx}"
                db_path = str(row.get("db_path", "task.db")).strip() or "task.db"
                expected_rows = _parse_expected_rows(
                    row.get("expected_rows", []),
                    field_name=f"query_checks[{idx}].expected_rows",
                    errors=errors,
                )
                query_checks.append(
                    VerificationQueryCheck(
                        id=query_id,
                        sql=query_sql,
                        expected_rows=expected_rows,
                        db_path=db_path,
                    )
                )

    if errors:
        return None, errors

    spec = VerificationSpec(
        source="VERIFICATION.json",
        exact_output_lines=exact_output_lines,
        required_files=required_files,
        file_content_patterns=tuple(file_content_patterns),
        query_checks=tuple(query_checks),
    )
    if spec.check_count() == 0:
        return None, ["empty_spec"]
    return spec, []


def _infer_verification_spec_from_task_text(task_text: str) -> VerificationSpec | None:
    """Fallback parser for task.md when no explicit VERIFICATION.json is present."""
    lines = task_text.splitlines()

    exact_output_lines: list[str] = []
    if re.search(r"\bprint\s+exactly\b", task_text, flags=re.IGNORECASE):
        for line in lines:
            match = re.match(r"^\s*[-*]\s*`([^`]+)`\s*$", line.strip())
            if match:
                exact_output_lines.append(match.group(1).strip())

    required_files: list[str] = []
    required_files.extend(
        re.findall(
            r"(?i)\bcreate\b[^`\n]*\bnamed\s+`([^`]+)`",
            task_text,
        )
    )
    required_files.extend(
        re.findall(
            r"(?i)\bwrite\b[^`\n]*`([^`]+)`",
            task_text,
        )
    )
    unique_required_files = tuple(dict.fromkeys(name.strip() for name in required_files if name.strip()))

    spec = VerificationSpec(
        source="task.md",
        exact_output_lines=tuple(dict.fromkeys(text for text in exact_output_lines if text)),
        required_files=unique_required_files,
    )
    if spec.check_count() == 0:
        return None
    return spec


def _load_verification_spec(task_dir: Path, task_text: str) -> tuple[VerificationSpec | None, list[str]]:
    spec_path = task_dir / "VERIFICATION.json"
    if spec_path.exists():
        return _load_verification_spec_from_json(spec_path)
    return _infer_verification_spec_from_task_text(task_text), []


def _event_text_lines(events: list[dict[str, Any]]) -> tuple[set[str], str]:
    """Extract normalized event output lines so exact-line probes stay deterministic."""
    raw_fragments: list[str] = []
    normalized_lines: set[str] = set()
    for row in events:
        if not isinstance(row, dict):
            continue
        for key in ("output", "error"):
            value = row.get(key)
            if not isinstance(value, str) or not value.strip():
                continue
            raw_fragments.append(value)
            for line in value.splitlines():
                stripped = line.strip()
                if stripped:
                    normalized_lines.add(stripped)
            try:
                payload = json.loads(value)
            except Exception:
                continue
            if isinstance(payload, dict):
                stdout = payload.get("stdout")
                if isinstance(stdout, str):
                    for line in stdout.splitlines():
                        stripped = line.strip()
                        if stripped:
                            normalized_lines.add(stripped)
    return normalized_lines, "\n".join(raw_fragments)


def _run_sqlite_query(db_path: Path, sql: str) -> tuple[list[list[str]] | None, str | None]:
    try:
        with sqlite3.connect(str(db_path)) as conn:
            rows = conn.execute(sql).fetchall()
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
    return [[str(col) for col in row] for row in rows], None


def _run_deterministic_probes(
    *,
    spec: VerificationSpec | None,
    events: list[dict[str, Any]],
    workspace: DomainWorkspace,
) -> DeterministicProbeResult:
    if spec is None or spec.check_count() <= 0:
        return DeterministicProbeResult(
            source="none",
            applicable=False,
            passed=False,
            score=0.0,
            reasons=["no_verification_spec"],
            evidence={},
        )

    checks_total = 0
    checks_passed = 0
    reasons: list[str] = []
    evidence: dict[str, Any] = {}
    output_lines, output_blob = _event_text_lines(events)

    if spec.exact_output_lines:
        checks_total += len(spec.exact_output_lines)
        matched: list[str] = []
        missing: list[str] = []
        for expected in spec.exact_output_lines:
            if expected in output_lines:
                checks_passed += 1
                matched.append(expected)
            else:
                missing.append(expected)
                reasons.append("missing_exact_output_line")
        evidence["exact_output_lines"] = {"matched": matched, "missing": missing}

    if spec.required_files:
        checks_total += len(spec.required_files)
        missing_files: list[str] = []
        for rel_path in spec.required_files:
            if (workspace.work_dir / rel_path).exists():
                checks_passed += 1
            else:
                missing_files.append(rel_path)
                reasons.append("missing_required_file")
        evidence["required_files"] = {"missing": missing_files}

    if spec.file_content_patterns:
        checks_total += len(spec.file_content_patterns)
        pattern_results: list[dict[str, Any]] = []
        for probe in spec.file_content_patterns:
            file_path = workspace.work_dir / probe.path
            if not file_path.exists():
                reasons.append("missing_required_file")
                pattern_results.append(
                    {"path": probe.path, "pattern": probe.pattern, "matched": False, "error": "missing_file"}
                )
                continue
            try:
                file_text = file_path.read_text(encoding="utf-8")
            except Exception as exc:
                reasons.append("file_pattern_mismatch")
                pattern_results.append(
                    {
                        "path": probe.path,
                        "pattern": probe.pattern,
                        "matched": False,
                        "error": f"{type(exc).__name__}:{exc}",
                    }
                )
                continue
            matched = bool(re.search(probe.pattern, file_text, flags=0))
            if matched:
                checks_passed += 1
            else:
                reasons.append("file_pattern_mismatch")
            pattern_results.append({"path": probe.path, "pattern": probe.pattern, "matched": matched})
        evidence["file_content_patterns"] = pattern_results

    if spec.query_checks:
        checks_total += len(spec.query_checks)
        query_results: list[dict[str, Any]] = []
        for probe in spec.query_checks:
            db_path = workspace.work_dir / probe.db_path
            actual_rows, query_error = _run_sqlite_query(db_path=db_path, sql=probe.sql)
            expected_rows = [list(row) for row in probe.expected_rows]
            matched = query_error is None and actual_rows == expected_rows
            if matched:
                checks_passed += 1
            else:
                reasons.append("query_check_mismatch" if query_error is None else "query_check_error")
            query_results.append(
                {
                    "id": probe.id,
                    "db_path": probe.db_path,
                    "sql": probe.sql,
                    "matched": matched,
                    "error": query_error,
                    "expected_rows": expected_rows,
                    "actual_rows": actual_rows,
                }
            )
        evidence["query_checks"] = query_results

    if output_blob:
        evidence["event_output_chars"] = len(output_blob)
    score = 0.0 if checks_total <= 0 else round(checks_passed / float(checks_total), 3)
    passed = checks_total > 0 and len(reasons) == 0
    return DeterministicProbeResult(
        source=spec.source,
        applicable=checks_total > 0,
        passed=passed,
        score=(1.0 if passed else score),
        reasons=sorted(set(reasons)),
        evidence=evidence,
    )


def _verification_spec_for_probe(spec: dict[str, Any] | None) -> VerificationSpec | None:
    """
    Convert runtime verifier dict into deterministic probe spec dataclass.
    """
    if not isinstance(spec, dict):
        return None
    exact_output_lines = tuple(
        _verification_runtime_helpers._dedupe_nonempty_text_rows(
            [str(value) for value in (spec.get("exact_output_lines", []) or [])]
        )
    )
    required_files = tuple(
        _verification_runtime_helpers._dedupe_nonempty_text_rows(
            [str(value) for value in (spec.get("required_files", []) or [])]
        )
    )
    file_content_patterns_rows = _verification_runtime_helpers._normalize_required_file_content_patterns(
        spec.get("required_file_content_patterns", [])
    )
    file_content_patterns: list[VerificationFilePattern] = []
    for row in file_content_patterns_rows:
        rel_path = str(row.get("path", "")).strip()
        for pattern in row.get("patterns", []):
            pattern_text = str(pattern).strip()
            if rel_path and pattern_text:
                file_content_patterns.append(
                    VerificationFilePattern(path=rel_path, pattern=pattern_text)
                )
    query_checks_rows = _verification_runtime_helpers._normalize_required_queries(
        spec.get("required_queries", [])
    )
    query_checks: list[VerificationQueryCheck] = []
    for row in query_checks_rows:
        expected_rows_raw = row.get("expected_rows", [])
        expected_rows = tuple(tuple(str(col) for col in rec) for rec in expected_rows_raw)
        db_path = str(row.get("db_path", "task.db")).strip() or "task.db"
        query_checks.append(
            VerificationQueryCheck(
                id=str(row.get("id", "")).strip() or "required_query",
                sql=str(row.get("sql", "")).strip(),
                expected_rows=expected_rows,
                db_path=db_path,
            )
        )
    probe_spec = VerificationSpec(
        source=str(spec.get("source", "")).strip() or "none",
        exact_output_lines=exact_output_lines,
        required_files=required_files,
        file_content_patterns=tuple(file_content_patterns),
        query_checks=tuple(query_checks),
    )
    if probe_spec.check_count() <= 0:
        return None
    return probe_spec
