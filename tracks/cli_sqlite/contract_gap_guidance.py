from __future__ import annotations

import json
import re
from typing import Any

from claude_print_runtime import clip_text
from tracks.cli_sqlite.domain_adapter import DomainAdapter


def _format_contract_gap_retry_prompt(
    *,
    unresolved_gaps: list[dict[str, Any]],
    deterministic_recipes: list[str] | None = None,
    injected_hints: list[str] | None = None,
    validator_evidence: list[str] | None = None,
    max_items: int = 5,
) -> str:
    lines = [
        "Deterministic contract gap check found unresolved requirements.",
        "Execute one focused correction step now. Do not stop yet.",
        "Unresolved gaps:",
    ]
    for index, gap in enumerate(unresolved_gaps[:max_items], start=1):
        reason = str(gap.get("reason_code", "")).strip() or "unknown_reason"
        gap_type = str(gap.get("gap_type", "")).strip() or "unknown_gap"
        detail = str(gap.get("detail", "")).strip()
        suffix = f" detail={detail}" if detail else ""
        lines.append(f"{index}. reason_code={reason} gap_type={gap_type}{suffix}")
        if reason == "required_query_mismatch":
            query_id = str(gap.get("query_id", "")).strip()
            query_sql = str(gap.get("query_sql", "")).strip()
            expected_rows = gap.get("expected_rows", [])
            actual_rows = gap.get("actual_rows", [])
            if query_id:
                lines.append(f"   - query_id={query_id}")
            if query_sql:
                lines.append(f"   - query_sql={query_sql}")
            if isinstance(expected_rows, list):
                lines.append(f"   - expected_rows={json.dumps(expected_rows, ensure_ascii=True)}")
            if isinstance(actual_rows, list):
                lines.append(f"   - actual_rows={json.dumps(actual_rows, ensure_ascii=True)}")
            lines.append(
                "   - correction rule: align database state so query_sql output exactly matches expected_rows."
            )
        elif reason == "matched_forbidden_pattern":
            lines.append(
                "   - correction rule: do not emit any SQL matching this forbidden pattern."
            )
            lines.append(
                "   - correction rule: use non-destructive alternatives only (INSERT/UPDATE/SELECT)."
            )
        elif reason == "too_many_errors":
            lines.append(
                "   - correction rule: keep next attempt deterministic with one mutating block max, then verify via SELECT queries."
            )
            lines.append(
                "   - correction rule: if verification still fails, stop and report remaining mismatch instead of guessing."
            )
    validator_rows = [str(row).strip() for row in (validator_evidence or []) if str(row).strip()]
    if validator_rows:
        lines.append("Deterministic validator evidence:")
        for row in validator_rows[:4]:
            lines.append(f"- {row}")
    deterministic_rows = [str(row).strip() for row in (deterministic_recipes or []) if str(row).strip()]
    if deterministic_rows:
        # Keep deterministic repair instructions in a dedicated section so the
        # executor can prioritize machine-like closure steps before free-form hints.
        lines.append("Deterministic repair block (execute exactly):")
        for row in deterministic_rows[:2]:
            lines.append(f"- {row}")
        lines.append("No alternate plan: run the listed steps exactly before stopping.")
    extra = [str(row).strip() for row in (injected_hints or []) if str(row).strip()]
    if extra:
        lines.append("Prior lessons matching these gaps:")
        for hint in extra[:2]:
            lines.append(f"- {hint}")
    lines.append("Return tool calls only after this message.")
    return "\n".join(lines)


def _fallback_rule_for_gap(gap: dict[str, Any]) -> str:
    reason = str(gap.get("reason_code", "")).strip() or "unknown_reason"
    gap_type = str(gap.get("gap_type", "")).strip() or "unknown_gap"
    detail = str(gap.get("detail", "")).strip()
    if reason == "required_query_mismatch":
        query_id = str(gap.get("query_id", "")).strip() or "required_query"
        query_sql = str(gap.get("query_sql", "")).strip()
        expected_rows = gap.get("expected_rows", [])
        query_suffix = f" query_sql={query_sql}" if query_sql else ""
        expected_suffix = (
            f" expected_rows={json.dumps(expected_rows, ensure_ascii=True)}"
            if isinstance(expected_rows, list)
            else ""
        )
        return (
            f"When reason_code={reason}, reconcile data so {query_id} matches exactly."
            f"{query_suffix}{expected_suffix}"
        )
    if reason == "too_many_errors":
        budget_detail = detail or "error budget exhausted"
        return (
            "When reason_code=too_many_errors, treat it as a strict error-budget breach "
            f"({budget_detail}). On next attempt use one deterministic mutating SQL block at most, "
            "then run required SELECT verification queries and stop."
        )
    if reason == "matched_forbidden_pattern":
        pattern_text = detail or str(gap.get("gap_signature", "")).strip() or "forbidden_sql_pattern"
        return (
            "When reason_code=matched_forbidden_pattern, never emit SQL matching "
            f"{pattern_text}. Use non-destructive alternatives only (INSERT/UPDATE/SELECT) "
            "and verify required queries before stop."
        )
    if detail:
        return f"When reason_code={reason}, resolve gap_type={gap_type} by fixing: {detail}."
    return f"When reason_code={reason}, resolve gap_type={gap_type} before stopping."


def _adapter_deterministic_gap_fix_recipes(
    *,
    adapter: DomainAdapter | None,
    task_id: str,
    unresolved_gaps: list[dict[str, Any]],
    max_items: int,
) -> list[str]:
    """Ask adapter for deterministic recipes, if the adapter exposes this hook.

    Why this exists:
    - Keeps core orchestrator domain-agnostic.
    - Allows optional domain recipes without hardcoding per-domain logic here.
    """
    if adapter is None:
        return []
    hook = getattr(adapter, "deterministic_gap_recipes", None)
    if not callable(hook):
        return []
    try:
        rows = hook(task_id=task_id, unresolved_gaps=unresolved_gaps, max_items=max_items)
    except Exception:
        return []
    if not isinstance(rows, list):
        return []
    clean: list[str] = []
    for row in rows:
        text = " ".join(str(row).split()).strip()
        if text:
            clean.append(text)
    return clean


def _deterministic_gap_fix_recipes(
    *,
    adapter: DomainAdapter | None,
    domain: str,
    task_id: str,
    unresolved_gaps: list[dict[str, Any]],
    max_items: int = 3,
) -> list[str]:
    """Build deterministic gap-fix recipes from unresolved contract gaps.

    First-principles split:
    - generic reason_code/gap_type fallback works for any domain/task.
    - optional domain-specific recipes provide executable command templates.
    """
    normalized_domain = str(domain).strip().lower()
    normalized_task_id = str(task_id).strip()
    dedup: set[str] = set()
    recipes: list[str] = []
    adapter_recipes = _adapter_deterministic_gap_fix_recipes(
        adapter=adapter,
        task_id=normalized_task_id,
        unresolved_gaps=unresolved_gaps,
        max_items=max_items,
    )
    for row in adapter_recipes:
        payload = f"[deterministic_recipe domain={normalized_domain} task_id={normalized_task_id}] {row}"
        key = payload.lower()
        if key in dedup:
            continue
        dedup.add(key)
        recipes.append(payload)
        if len(recipes) >= max(1, int(max_items)):
            return recipes

    for row in unresolved_gaps:
        if not isinstance(row, dict):
            continue
        recipe = _fallback_rule_for_gap(row)
        text = " ".join(str(recipe).split()).strip()
        if not text:
            continue
        # Include compact routing context so retrieval matching can anchor by
        # domain/task without overfitting to one exact task string.
        payload = f"[deterministic_recipe domain={normalized_domain} task_id={normalized_task_id}] {text}"
        key = payload.lower()
        if key in dedup:
            continue
        dedup.add(key)
        recipes.append(payload)
        if len(recipes) >= max(1, int(max_items)):
            break
    return recipes


def _build_low_confidence_clarifying_question(
    *,
    task_id: str,
    missing_verification_lines: list[str],
    unresolved_gaps: list[dict[str, Any]],
) -> str:
    """
    Build a deterministic clarification request when probes are inconclusive.

    No model generation is used here; output is template-based and stable.
    """
    if missing_verification_lines:
        quoted = ", ".join(f"`{line}`" for line in missing_verification_lines[:3])
        return (
            f"Low-confidence verification for task `{task_id}` is inconclusive. "
            f"Please confirm the exact expected verification line(s): {quoted}."
        )
    if unresolved_gaps:
        gap = unresolved_gaps[0]
        reason = str(gap.get("reason_code", "")).strip() or "unknown_reason"
        gap_type = str(gap.get("gap_type", "")).strip() or "unknown_gap"
        detail = str(gap.get("detail", "")).strip()
        detail_suffix = f" detail={detail}" if detail else ""
        return (
            f"Low-confidence verification for task `{task_id}` needs one deterministic success signal. "
            f"Current unresolved gap: reason_code={reason} gap_type={gap_type}{detail_suffix}. "
            "Please provide exact expected output (line/file/query rows)."
        )
    return (
        f"Low-confidence verification for task `{task_id}` is inconclusive. "
        "Please provide one deterministic success signal: exact stdout line, file path+content, or SQL query rows."
    )


def _build_sqlite_validator_guidance_from_contract(
    *,
    contract: dict[str, Any],
    max_queries: int = 4,
) -> str:
    """
    Render deterministic validator steps from CONTRACT required queries.

    This keeps validation protocol machine-driven (contract source of truth)
    instead of relying on ad-hoc prompt prose per task.
    """
    if not isinstance(contract, dict):
        return ""
    signals = contract.get("signals", {})
    if not isinstance(signals, dict):
        return ""
    required_queries = signals.get("required_queries", [])
    if not isinstance(required_queries, list) or not required_queries:
        return ""
    lines = [
        "Deterministic validator protocol (from CONTRACT):",
        "- Before final stop, run these validator queries with run_sqlite and verify expected rows exactly.",
    ]
    added = 0
    for row in required_queries:
        if not isinstance(row, dict):
            continue
        query_id = str(row.get("id", "")).strip() or f"query_{added + 1}"
        query_sql = str(row.get("sql", "")).strip()
        expected_rows = row.get("expected_rows", [])
        if not query_sql:
            continue
        lines.append(f"- validator[{query_id}] sql={query_sql}")
        if isinstance(expected_rows, list):
            lines.append(f"  expected_rows={json.dumps(expected_rows, ensure_ascii=True)}")
        added += 1
        if added >= max(1, int(max_queries)):
            break
    if added <= 0:
        return ""
    lines.append("- If any validator mismatches, correct data and rerun validators before stopping.")
    return "\n".join(lines)


def _contract_pattern_to_hint_text(pattern: str, *, max_chars: int = 140) -> str:
    """
    Convert a regex-like contract pattern into a short, human-readable hint.

    This keeps contract-derived guidance useful for smaller executor models
    without hardcoding task-specific command recipes in Python.
    """
    text = str(pattern or "").strip()
    if not text:
        return ""
    # Strip common regex wrappers/tokens so the model sees a likely command
    # shape instead of raw regex noise.
    simplified = text
    for token in ("(?is)", "(?si)", "(?s)", "(?i)", "^", "$", "\\b"):
        simplified = simplified.replace(token, "")
    replacements = (
        ("\\s+", " "),
        ("\\s*", " "),
        ("\\.", "."),
        ("\\/", "/"),
    )
    for source, target in replacements:
        simplified = simplified.replace(source, target)
    simplified = re.sub(r"\s+", " ", simplified).strip()
    if not simplified:
        simplified = text
    return clip_text(simplified, max_chars=max_chars)


def _build_contract_execution_guidance_from_contract(
    *,
    contract: dict[str, Any],
    max_required: int = 4,
    max_forbidden: int = 2,
) -> str:
    """
    Build a generic contract-closure checklist from required/forbidden patterns.

    Why this exists:
    - Domain adapters can define contracts, but prompt guidance was sqlite-only.
    - Tight-step tasks fail when models forget one required action.
    - This gives every domain the same deterministic closure checklist source.
    """
    if not isinstance(contract, dict):
        return ""
    signals = contract.get("signals", {})
    if not isinstance(signals, dict):
        return ""
    required = [str(row).strip() for row in signals.get("required_event_patterns", []) if str(row).strip()]
    forbidden = [str(row).strip() for row in signals.get("forbidden_event_patterns", []) if str(row).strip()]
    if not required and not forbidden:
        return ""

    lines: list[str] = [
        "Deterministic contract closure checklist:",
    ]
    if required:
        lines.append("- Required command/event coverage before stop:")
        added_required = 0
        for pattern in required:
            hint = _contract_pattern_to_hint_text(pattern)
            if not hint:
                continue
            lines.append(f"  - required: {hint}")
            added_required += 1
            if added_required >= max(1, int(max_required)):
                break
    if forbidden:
        lines.append("- Forbidden command/event patterns to avoid:")
        added_forbidden = 0
        for pattern in forbidden:
            hint = _contract_pattern_to_hint_text(pattern)
            if not hint:
                continue
            lines.append(f"  - avoid: {hint}")
            added_forbidden += 1
            if added_forbidden >= max(1, int(max_forbidden)):
                break
    lines.append("- If checklist items are unmet, repair and verify before final stop.")
    return "\n".join(lines)


def _build_gap_row(*, reason_code: str, gap_type: str, detail: str) -> dict[str, Any]:
    text = str(detail).strip()
    return {
        "reason_code": reason_code,
        "gap_type": gap_type,
        "detail": text,
        "gap_signature": f"{reason_code}|{gap_type}|{text}",
    }

