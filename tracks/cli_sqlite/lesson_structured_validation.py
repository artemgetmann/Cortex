from __future__ import annotations

import re
from typing import Any

from tracks.cli_sqlite.domain_adapter import DomainAdapter


def _parse_action_tool_name(action_template: str) -> str:
    text = str(action_template or "").strip()
    if not text:
        return ""
    match = re.match(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", text)
    if not match:
        return ""
    return str(match.group(1)).strip()


def _action_template_is_placeholder_like(action_template: str) -> bool:
    text = str(action_template or "").strip().lower()
    if not text:
        return True
    # Reject explicit placeholder spans like "<value>" but allow shell
    # redirection operators used in real command templates.
    if re.search(r"<[^>\n]{1,40}>", text):
        return True
    placeholder_tokens = (
        "...",
        "todo",
        "tbd",
        "placeholder",
        "example",
        "fill_here",
    )
    return any(token in text for token in placeholder_tokens)


def _action_template_has_named_args(action_template: str) -> bool:
    text = str(action_template or "").strip()
    match = re.match(r"^\s*[a-zA-Z_][a-zA-Z0-9_]*\s*\((.*)\)\s*$", text, re.DOTALL)
    if not match:
        return False
    inner = str(match.group(1)).strip()
    if not inner:
        return False
    # Require at least one named argument to avoid vague "tool()" templates.
    return "=" in inner


def _expected_evidence_is_anchored(
    *,
    expected_evidence: str,
    resolved_signature: str,
    resolved_reason: str,
    resolved_gap_type: str,
    matched_row: dict[str, Any],
) -> bool:
    text = str(expected_evidence or "").strip().lower()
    if not text:
        return False
    anchors = {
        str(resolved_signature or "").strip().lower(),
        str(resolved_reason or "").strip().lower(),
        str(resolved_gap_type or "").strip().lower(),
        str(matched_row.get("query_id", "")).strip().lower(),
        str(matched_row.get("detail", "")).strip().lower(),
    }
    # Keep only meaningful anchors and avoid tiny noise tokens.
    clean_anchors = {anchor for anchor in anchors if len(anchor) >= 3}
    if not clean_anchors:
        return True
    if any(anchor in text for anchor in clean_anchors):
        return True

    # Fallback: allow semantic anchoring via meaningful tokens extracted from
    # gap metadata/detail (handles regex-like signatures such as
    # (?is)git\\s+format-patch... that won't appear verbatim in evidence text).
    token_source = " ".join(
        [
            str(resolved_reason or ""),
            str(resolved_gap_type or ""),
            str(matched_row.get("query_id", "") or ""),
            str(matched_row.get("detail", "") or ""),
        ]
    ).lower()
    raw_tokens = re.findall(r"[a-z0-9_./-]{3,}", token_source)
    stop_tokens = {
        "missing",
        "required",
        "pattern",
        "query",
        "reason",
        "code",
        "type",
        "detail",
        "event",
        "file",
        "content",
    }
    semantic_tokens = {tok for tok in raw_tokens if tok not in stop_tokens and len(tok) >= 4}
    if not semantic_tokens:
        return False
    return any(tok in text for tok in semantic_tokens)


def _allowed_action_tools_for_adapter(*, adapter: DomainAdapter, opaque_tools: bool) -> set[str]:
    alias_map = adapter.build_alias_map(opaque=opaque_tools)
    allowed = {
        str(adapter.executor_tool_name).strip(),
        "read_skill",
        "show_fixture",
    }
    for api_name, canonical in alias_map.items():
        api_clean = str(api_name).strip()
        canonical_clean = str(canonical).strip()
        if api_clean:
            allowed.add(api_clean)
        if canonical_clean:
            allowed.add(canonical_clean)
    return {value for value in allowed if value}


def _validate_structured_model_lesson(
    *,
    lesson: Any,
    unresolved_gap_rows: list[dict[str, Any]],
    allowed_action_tools: set[str],
) -> tuple[bool, str, dict[str, str]]:
    """
    Validate structured lesson fields emitted by executor self-reflection.

    Enforced invariants:
    - trigger must bind to current unresolved gaps
    - action must be tool-shaped and allowed by domain adapter
    - expected evidence must be present for deterministic post-run checks
    """
    trigger_gap_signature = str(getattr(lesson, "trigger_gap_signature", "")).strip()
    reason_code = str(getattr(lesson, "reason_code", "")).strip()
    gap_type = str(getattr(lesson, "gap_type", "")).strip()
    action_template = " ".join(str(getattr(lesson, "action_template", "")).split()).strip()
    expected_evidence = " ".join(str(getattr(lesson, "expected_evidence", "")).split()).strip()
    unresolved_by_signature = {
        str(row.get("gap_signature", "")).strip(): row
        for row in unresolved_gap_rows
        if str(row.get("gap_signature", "")).strip()
    }
    unresolved_by_reason_type = {
        (str(row.get("reason_code", "")).strip(), str(row.get("gap_type", "")).strip()): row
        for row in unresolved_gap_rows
        if str(row.get("reason_code", "")).strip() and str(row.get("gap_type", "")).strip()
    }

    if not trigger_gap_signature:
        return False, "missing_trigger_gap_signature", {}
    matched_row = unresolved_by_signature.get(trigger_gap_signature)
    if matched_row is None:
        if reason_code and gap_type:
            matched_row = unresolved_by_reason_type.get((reason_code, gap_type))
        if matched_row is None:
            return False, "unbound_trigger_gap_signature", {}

    if not action_template:
        return False, "missing_action_template", {}
    if _action_template_is_placeholder_like(action_template):
        return False, "invalid_action_template_placeholder", {}
    tool_name = _parse_action_tool_name(action_template)
    if not tool_name:
        return False, "invalid_action_template_shape", {}
    if not _action_template_has_named_args(action_template):
        return False, "invalid_action_template_shape", {}
    if tool_name not in allowed_action_tools:
        return False, "invalid_action_template_tool", {}

    if not expected_evidence:
        return False, "missing_expected_evidence", {}

    # Canonicalize to the contract row that actually matched.
    #
    # Why this matters:
    # - Models often output a partial trigger (for example only the detail regex).
    # - If we store the partial trigger as-is, strict retrieval cannot bind it later.
    # - Using the matched unresolved row's canonical triplet keeps write/read symmetric.
    resolved_reason = str(matched_row.get("reason_code", "") or reason_code).strip()
    resolved_gap_type = str(matched_row.get("gap_type", "") or gap_type).strip()
    resolved_signature = str(matched_row.get("gap_signature", "") or trigger_gap_signature).strip()
    if not (resolved_reason and resolved_gap_type and resolved_signature):
        return False, "missing_structured_gap_fields", {}
    if not _expected_evidence_is_anchored(
        expected_evidence=expected_evidence,
        resolved_signature=resolved_signature,
        resolved_reason=resolved_reason,
        resolved_gap_type=resolved_gap_type,
        matched_row=matched_row,
    ):
        return False, "expected_evidence_unanchored", {}

    return True, "", {
        "trigger_gap_signature": resolved_signature,
        "reason_code": resolved_reason,
        "gap_type": resolved_gap_type,
        "action_template": action_template,
        "expected_evidence": expected_evidence,
    }


def _extract_action_template_from_legacy_lesson(
    *,
    lesson_text: str,
    executor_tool_name: str,
) -> str:
    """Extract executable action template from legacy free-text lesson content.

    Why this exists:
    - Strict mode expects structured lessons (`action_template`, `gap_signature`)
      but legacy generators often emit only prose.
    - We salvage clearly executable commands from prose (for example
      `CORRECT: git init ...`) and convert them into tool-call templates.
    """

    text = str(lesson_text or "").strip()
    if not text:
        return ""

    # If lesson already contains a tool-call snippet, keep it as-is when valid.
    existing_call = re.search(r"([a-zA-Z_][a-zA-Z0-9_]*\s*\([^)]*\))", text)
    if existing_call:
        candidate_call = " ".join(str(existing_call.group(1)).split()).strip()
        if (
            candidate_call
            and not _action_template_is_placeholder_like(candidate_call)
            and _action_template_has_named_args(candidate_call)
        ):
            return candidate_call

    if str(executor_tool_name).strip() == "run_bash":
        # Prefer explicit "CORRECT: <command>" span if present.
        correct_match = re.search(r"CORRECT:\s*(.+?)(?:\s+WHY:|$)", text, re.IGNORECASE)
        command_text = str(correct_match.group(1) if correct_match else text).strip()
        command_text = command_text.strip("`").strip().rstrip(".").rstrip(";").strip()
        if command_text and re.search(r"^(git|bash|sh|python|python3|cp|mv|rm|mkdir|echo|printf|cat|grep|sed|awk)\b", command_text):
            escaped = command_text.replace("\\", "\\\\").replace('"', '\\"')
            return f'run_bash(command="{escaped}")'
        return ""

    if str(executor_tool_name).strip() == "run_sqlite":
        sql_match = re.search(r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\b.+", text, re.IGNORECASE)
        if not sql_match:
            return ""
        sql_text = str(sql_match.group(0)).strip().rstrip(".")
        escaped_sql = sql_text.replace("\\", "\\\\").replace('"', '\\"')
        return f'run_sqlite(sql="{escaped_sql}")'

    return ""
