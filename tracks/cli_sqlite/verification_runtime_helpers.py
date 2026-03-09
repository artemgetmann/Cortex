from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

_FILE_TOKEN_RE = re.compile(
    r"\b([A-Za-z0-9_.\\/-]+\.(?:txt|md|json|csv|tsv|sql|patch|diff|xlsx|xlsm|yaml|yml|log))\b"
)


def _extract_verification_lines(task_text: str, *, max_lines: int = 6) -> list[str]:
    """
    Parse explicit `Print exactly ... verification line(s)` requirements from task text.

    This parser is intentionally strict and deterministic: we only extract
    backtick-wrapped bullet lines directly under the marker section.
    """
    if not str(task_text).strip():
        return []
    marker = re.compile(
        r"(?:print\s+exactly\s+(?:this|these)(?:\s+\d+)?\s+verification\s+line|verify|verification|prove|confirm|show)",
        re.IGNORECASE,
    )
    lines = str(task_text).splitlines()
    capture = False
    collected: list[str] = []
    for raw_line in lines:
        line = str(raw_line)
        stripped = line.strip()
        if marker.search(line):
            inline_matches = re.findall(r"`([^`]+)`", line)
            for match in inline_matches:
                value = str(match).strip()
                if value:
                    collected.append(value)
            capture = True
            continue
        if not capture:
            continue
        if stripped.startswith("Constraints:") or stripped.startswith("Goal:"):
            break
        if not stripped:
            # Keep scanning through single blank lines in case the marker uses
            # a compact markdown style with spacing before bullets.
            continue
        bullet_match = re.match(r"^\s*(?:[-*]|\d+[.)])\s+`([^`]+)`\s*$", line)
        if bullet_match:
            value = str(bullet_match.group(1)).strip()
            if value:
                collected.append(value)
            if len(collected) >= max(1, int(max_lines)):
                break
            continue
        # If capture started and we hit non-bullet prose, stop deterministically.
        if collected:
            break
    deduped: list[str] = []
    seen: set[str] = set()
    for row in collected:
        if row in seen:
            continue
        seen.add(row)
        deduped.append(row)
    lowered = str(task_text).lower()
    if (
        "repo status is clean" in lowered
        or "final repo status is clean" in lowered
        or "working tree is clean" in lowered
    ):
        if "nothing to commit, working tree clean" not in seen:
            deduped.append("nothing to commit, working tree clean")
    return deduped[: max(1, int(max_lines))]


def _dedupe_nonempty_text_rows(values: list[str]) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for row in values:
        text = str(row).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        rows.append(text)
    return rows


def _extract_required_files_from_task_text(task_text: str, *, max_files: int = 8) -> list[str]:
    """
    Infer required output files from imperative task lines.

    We intentionally keep this narrow (Create/Write/Generate/Save/Output + backticks)
    to avoid speculative checks that produce noisy verifier failures.
    """
    if not str(task_text).strip():
        return []
    files: list[str] = []
    pattern = re.compile(
        r"\b(?:create|write|generate|save|output)\s+`([^`]+)`",
        re.IGNORECASE,
    )
    file_like_verbs = re.compile(
        r"\b(?:create|write|generate|save|output|produce|return|deliver)\b",
        re.IGNORECASE,
    )
    for line in str(task_text).splitlines():
        for match in pattern.findall(line):
            text = str(match).strip()
            if text:
                files.append(text)
            if len(files) >= max(1, int(max_files)):
                return _dedupe_nonempty_text_rows(files)
        if file_like_verbs.search(line):
            for match in _FILE_TOKEN_RE.finditer(line):
                text = str(match.group(1)).strip()
                if text:
                    prefix_full = line[: match.start()].lower()
                    # Treat "from <file>" as input fixture reference, not a
                    # required output artifact.
                    if re.search(r"\bfrom\s+`?\s*$", prefix_full):
                        continue
                    files.append(text)
                if len(files) >= max(1, int(max_files)):
                    return _dedupe_nonempty_text_rows(files)
    # Fallback: if task text explicitly references "file(s)" but does not use
    # backticks, still infer common file-like tokens as deterministic anchors.
    lowered = str(task_text).lower()
    if "file" in lowered or "files" in lowered:
        for token in _FILE_TOKEN_RE.findall(str(task_text)):
            text = str(token).strip()
            if text:
                files.append(text)
            if len(files) >= max(1, int(max_files)):
                break
    return _dedupe_nonempty_text_rows(files)


def _extract_required_file_content_patterns_from_task_text(
    task_text: str,
    *,
    max_keys_per_file: int = 12,
) -> list[dict[str, Any]]:
    """
    Infer file-key expectations from markdown text like:
    `Write `report_manifest.json` with exact keys: `k1`, `k2``.
    """
    if not str(task_text).strip():
        return []
    lines = str(task_text).splitlines()
    rows: list[dict[str, Any]] = []
    for idx, raw_line in enumerate(lines):
        line = str(raw_line)
        match = re.search(
            r"\bwrite\s+`([^`]+)`\s+with\s+exact\s+keys?\s*:\s*(.*)$",
            line,
            flags=re.IGNORECASE,
        )
        if not match:
            continue
        rel_path = str(match.group(1)).strip()
        if not rel_path:
            continue
        key_names: list[str] = [str(name).strip() for name in re.findall(r"`([^`]+)`", str(match.group(2)))]
        cursor = idx + 1
        while cursor < len(lines) and len(key_names) < max(1, int(max_keys_per_file)):
            candidate = str(lines[cursor]).strip()
            if not candidate:
                if key_names:
                    break
                cursor += 1
                continue
            if candidate.startswith("Constraints:") or candidate.startswith("Goal:"):
                break
            inline = [str(name).strip() for name in re.findall(r"`([^`]+)`", candidate)]
            if inline:
                key_names.extend(inline)
                cursor += 1
                continue
            if key_names:
                break
            cursor += 1
        normalized_keys = _dedupe_nonempty_text_rows(key_names)[: max(1, int(max_keys_per_file))]
        if not normalized_keys:
            continue
        patterns = [rf"\"{re.escape(key)}\"\s*:" for key in normalized_keys]
        rows.append({"path": rel_path, "patterns": patterns})
    return rows


def _normalize_required_file_content_patterns(raw: Any) -> list[dict[str, Any]]:
    """Normalize `required_file_content_patterns` from VERIFICATION.json."""
    rows: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return rows
    for item in raw:
        if not isinstance(item, dict):
            continue
        rel_path = str(item.get("path", "")).strip()
        if not rel_path:
            continue
        raw_patterns = item.get("patterns")
        if not isinstance(raw_patterns, list):
            single = str(item.get("pattern", "")).strip()
            raw_patterns = [single] if single else []
        patterns = _dedupe_nonempty_text_rows([str(value).strip() for value in raw_patterns])
        if not patterns:
            continue
        rows.append({"path": rel_path, "patterns": patterns})
    return rows


def _normalize_expected_rows(expected_rows: Any) -> list[list[str]]:
    """Normalize expected rows into deterministic string matrix."""
    normalized: list[list[str]] = []
    if not isinstance(expected_rows, list):
        return normalized
    for row in expected_rows:
        if not isinstance(row, list):
            continue
        normalized.append([str(cell) for cell in row])
    return normalized


def _normalize_required_queries(raw: Any) -> list[dict[str, Any]]:
    """Normalize verifier query specs into deterministic rows."""
    rows: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return rows
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        query_sql = str(item.get("sql", "")).strip()
        if not query_sql:
            continue
        query_id = str(item.get("id", "")).strip() or f"required_query_{idx + 1}"
        expected_rows = _normalize_expected_rows(item.get("expected_rows", []))
        db_path = str(item.get("db_path", "")).strip()
        row = {
            "id": query_id,
            "sql": query_sql,
            "expected_rows": expected_rows,
        }
        if db_path:
            row["db_path"] = db_path
        rows.append(row)
    return rows


def _load_verification_spec(
    *,
    tasks_root: Path,
    task_id: str,
    task_text: str,
) -> dict[str, Any]:
    """
    Load deterministic verifier anchors from task text and optional JSON spec.

    Priority:
    - infer narrow anchors from task.md (lines/files/patterns)
    - VERIFICATION.json fields override inferred values
    """
    inferred_lines = _extract_verification_lines(task_text)
    inferred_files = _extract_required_files_from_task_text(task_text)
    inferred_file_patterns = _extract_required_file_content_patterns_from_task_text(task_text)

    spec: dict[str, Any] = {
        "source": "task_md",
        "source_path": str(tasks_root / task_id / "task.md"),
        "exact_output_lines": inferred_lines,
        "required_files": inferred_files,
        "required_file_content_patterns": inferred_file_patterns,
        "required_queries": [],
        "db_path": "",
    }

    verification_path = tasks_root / task_id / "VERIFICATION.json"
    if not verification_path.exists():
        return spec
    try:
        payload = json.loads(verification_path.read_text(encoding="utf-8"))
    except Exception:
        spec["source"] = "VERIFICATION.json_invalid"
        return spec
    if not isinstance(payload, dict):
        spec["source"] = "VERIFICATION.json_invalid"
        return spec

    # Explicit JSON entries replace inferred values for the same field.
    if "exact_output_lines" in payload:
        spec["exact_output_lines"] = _dedupe_nonempty_text_rows(
            [str(value) for value in payload.get("exact_output_lines", [])]
            if isinstance(payload.get("exact_output_lines"), list)
            else []
        )
    if "required_files" in payload:
        spec["required_files"] = _dedupe_nonempty_text_rows(
            [str(value) for value in payload.get("required_files", [])]
            if isinstance(payload.get("required_files"), list)
            else []
        )
    if "required_file_content_patterns" in payload:
        spec["required_file_content_patterns"] = _normalize_required_file_content_patterns(
            payload.get("required_file_content_patterns")
        )
    if "required_queries" in payload:
        spec["required_queries"] = _normalize_required_queries(payload.get("required_queries"))
    db_path = str(payload.get("db_path", "")).strip()
    if db_path:
        spec["db_path"] = db_path

    spec["source"] = "VERIFICATION.json"
    spec["source_path"] = str(verification_path)
    return spec


def _run_required_files_probe(*, work_dir: Path, required_files: list[str]) -> dict[str, Any]:
    missing: list[str] = []
    present: list[str] = []
    for rel_path in required_files:
        target = work_dir / rel_path
        if target.exists():
            present.append(rel_path)
        else:
            missing.append(rel_path)
    return {
        "probe_id": "required_files",
        "applicable": bool(required_files),
        "passed": len(missing) == 0,
        "detail": "matched" if len(missing) == 0 else "missing_required_file",
        "evidence": {
            "work_dir": str(work_dir),
            "required_files": list(required_files),
            "present_files": present,
            "missing_files": missing,
        },
    }


def _run_required_file_content_patterns_probe(
    *,
    work_dir: Path,
    required_file_content_patterns: list[dict[str, Any]],
) -> dict[str, Any]:
    matched: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    for row in required_file_content_patterns:
        rel_path = str(row.get("path", "")).strip()
        patterns = row.get("patterns", [])
        if not rel_path or not isinstance(patterns, list):
            continue
        target = work_dir / rel_path
        file_text = ""
        if target.exists():
            try:
                file_text = target.read_text(encoding="utf-8", errors="replace")
            except Exception:
                file_text = ""
        for pattern in patterns:
            pattern_text = str(pattern).strip()
            if not pattern_text:
                continue
            if file_text and re.search(pattern_text, file_text, flags=0):
                matched.append({"path": rel_path, "pattern": pattern_text})
            else:
                missing.append({"path": rel_path, "pattern": pattern_text})
    return {
        "probe_id": "required_file_content_patterns",
        "applicable": bool(required_file_content_patterns),
        "passed": len(missing) == 0,
        "detail": "matched" if len(missing) == 0 else "missing_required_file_content_pattern",
        "evidence": {
            "work_dir": str(work_dir),
            "matched": matched,
            "missing": missing,
        },
    }


def _resolve_verification_db_path(*, work_dir: Path, db_path_hint: str) -> Path:
    hint = str(db_path_hint).strip()
    if not hint:
        return work_dir / "task.db"
    candidate = Path(hint)
    if candidate.is_absolute():
        return candidate
    return work_dir / candidate


def _run_required_query_probe(*, db_path: Path, query_spec: dict[str, Any]) -> dict[str, Any]:
    query_id = str(query_spec.get("id", "")).strip() or "required_query"
    query_sql = str(query_spec.get("sql", "")).strip()
    expected_rows = _normalize_expected_rows(query_spec.get("expected_rows", []))
    if not query_sql:
        return {
            "probe_id": f"required_query:{query_id}",
            "applicable": False,
            "passed": False,
            "detail": "missing_query_sql",
            "evidence": {},
        }
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.execute(query_sql)
            actual_rows = [[str(cell) for cell in row] for row in cursor.fetchall()]
    except Exception as exc:
        return {
            "probe_id": f"required_query:{query_id}",
            "applicable": True,
            "passed": False,
            "detail": "required_query_error",
            "evidence": {
                "query_id": query_id,
                "query_sql": query_sql,
                "db_path": str(db_path),
                "error": f"{type(exc).__name__}: {exc}",
            },
        }
    passed = actual_rows == expected_rows
    return {
        "probe_id": f"required_query:{query_id}",
        "applicable": True,
        "passed": bool(passed),
        "detail": "matched" if passed else "required_query_mismatch",
        "evidence": {
            "query_id": query_id,
            "query_sql": query_sql,
            "db_path": str(db_path),
            "expected_rows": expected_rows,
            "actual_rows": actual_rows,
        },
    }


def _collect_event_text_blobs(events: list[dict[str, Any]]) -> str:
    """Collect textual event outputs/errors for deterministic probe checks."""
    chunks: list[str] = []
    for row in events:
        if not isinstance(row, dict):
            continue
        output = row.get("output")
        error = row.get("error")
        if isinstance(output, str) and output.strip():
            chunks.append(output)
        if isinstance(error, str) and error.strip():
            chunks.append(error)
    return "\n".join(chunks)


def _run_sqlite_gap_query_probe(*, db_path: Path, gap: dict[str, Any]) -> dict[str, Any]:
    """
    Probe unresolved sqlite required_query gaps with direct deterministic SQL.

    This avoids extra model calls and validates exact expected rows.
    """
    query_id = str(gap.get("query_id", "")).strip() or "required_query"
    query_sql = str(gap.get("query_sql", "")).strip()
    expected_rows = _normalize_expected_rows(gap.get("expected_rows", []))
    if not query_sql:
        return {
            "probe_id": f"sqlite_required_query:{query_id}",
            "applicable": False,
            "passed": False,
            "detail": "missing_query_sql",
            "evidence": {},
        }
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.execute(query_sql)
            actual = [[str(cell) for cell in row] for row in cursor.fetchall()]
    except Exception as exc:
        return {
            "probe_id": f"sqlite_required_query:{query_id}",
            "applicable": True,
            "passed": False,
            "detail": f"query_error:{type(exc).__name__}:{exc}",
            "evidence": {
                "query_id": query_id,
                "query_sql": query_sql,
            },
        }
    passed = actual == expected_rows
    return {
        "probe_id": f"sqlite_required_query:{query_id}",
        "applicable": True,
        "passed": bool(passed),
        "detail": "matched" if passed else "required_query_mismatch",
        "evidence": {
            "query_id": query_id,
            "query_sql": query_sql,
            "expected_rows": expected_rows,
            "actual_rows": actual,
        },
    }
