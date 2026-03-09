from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from tracks.cli_sqlite.lesson_store_v2 import load_lesson_records

_PLACEBO_HINT_BANK: tuple[str, ...] = (
    "Re-read the task goal and verify all required outputs before stopping.",
    "Use deterministic checks and avoid guessing when a requirement is unclear.",
    "Confirm filenames, query outputs, and exact required patterns before finalizing.",
    "Prioritize contract closure over stylistic or optional cleanup steps.",
    "When errors recur, simplify the plan and verify intermediate outputs explicitly.",
)
_MAX_INLINE_HINT_CHARS = 420
_MAX_INLINE_ACTION_CHARS = 220
_MAX_INLINE_EVIDENCE_CHARS = 180
_UNSAFE_HINT_MARKERS: tuple[str, ...] = (
    "```",
    "<<",
    "$(",
    "\x00",
)


def _placebo_hint_for_lesson(*, lesson_id: str, task_id: str, domain: str) -> str:
    token = f"{domain}|{task_id}|{lesson_id}".encode("utf-8", "ignore")
    digest = hashlib.sha256(token).hexdigest()
    idx = int(digest[:8], 16) % len(_PLACEBO_HINT_BANK)
    return f"PLACEBO_CONTROL[{digest[:6]}]: {_PLACEBO_HINT_BANK[idx]}"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _squash_ws(text: str) -> str:
    return " ".join(str(text or "").split())


def _coarse_gap_anchor(lesson: Any) -> str:
    signature = str(getattr(lesson, "gap_signature", "")).strip()
    if signature:
        return signature[:120]
    reason = str(getattr(lesson, "reason_code", "")).strip()
    gap_type = str(getattr(lesson, "gap_type", "")).strip()
    if reason or gap_type:
        return f"{reason}|{gap_type}".strip("|")
    return "generic_gap"


def _looks_like_giant_command_blob(text: str) -> bool:
    payload = _squash_ws(text)
    if not payload:
        return False
    if len(payload) > _MAX_INLINE_HINT_CHARS:
        return True
    if "run_bash(command=" in payload and (payload.count(";") >= 4 or payload.count("&&") >= 3):
        return True
    if payload.count("run_bash(") >= 2:
        return True
    if "HINT from prior sessions" in payload:
        return True
    return False


def _action_template_is_inline_safe(action_template: str) -> bool:
    text = _squash_ws(action_template)
    if not text:
        return False
    if len(text) > _MAX_INLINE_ACTION_CHARS:
        return False
    if "\n" in action_template or "```" in action_template:
        return False
    if "run_bash(command=" in text and (text.count(";") >= 4 or text.count("&&") >= 3):
        return False
    return True


def _lesson_trust_band(lesson: Any) -> str:
    """
    Soft firewall trust bands:
    - trusted: proven and low-risk
    - uncertain: available but lower confidence
    - risky: keep in memory, but do not inject as executable command text
    """
    status = str(getattr(lesson, "status", "")).strip().lower()
    reliability = _safe_float(getattr(lesson, "reliability", 0.5), default=0.5)
    harmful_count = max(0, _safe_int(getattr(lesson, "harmful_count", 0), default=0))
    contradiction_losses = max(0, _safe_int(getattr(lesson, "contradiction_losses", 0), default=0))
    major_regressions = max(0, _safe_int(getattr(lesson, "major_regressions", 0), default=0))

    if status in {"suppressed", "archived"}:
        return "risky"
    if contradiction_losses > 0 or major_regressions > 0:
        return "risky"
    if harmful_count >= 2 or reliability < 0.30:
        return "risky"
    if status == "promoted" and reliability >= 0.55 and harmful_count == 0:
        return "trusted"
    if reliability >= 0.70 and harmful_count == 0:
        return "trusted"
    return "uncertain"


def _render_runtime_lesson_hint(
    *,
    lesson: Any,
    use_placebo: bool = False,
    task_id: str = "",
    domain: str = "",
) -> tuple[str, str, str]:
    """
    Build one runtime hint with a soft firewall.

    Returns:
    - hint text
    - trust band: trusted|uncertain|risky|placebo
    - mode: direct_action|summary|placebo
    """
    lesson_id = str(getattr(lesson, "lesson_id", ""))
    if use_placebo:
        return (
            _placebo_hint_for_lesson(lesson_id=lesson_id, task_id=task_id, domain=domain),
            "placebo",
            "placebo",
        )

    trust_band = _lesson_trust_band(lesson)
    gap_signature = str(getattr(lesson, "gap_signature", "")).strip()
    action_template = _squash_ws(str(getattr(lesson, "action_template", "")).strip())
    expected_evidence = _squash_ws(str(getattr(lesson, "expected_evidence", "")).strip())[:_MAX_INLINE_EVIDENCE_CHARS]
    if trust_band != "risky" and gap_signature and action_template and expected_evidence and _action_template_is_inline_safe(action_template):
        return (
            f"WHEN gap_signature={gap_signature}: {action_template} EXPECT: {expected_evidence}",
            trust_band,
            "direct_action",
        )

    raw_rule = _squash_ws(str(getattr(lesson, "rule_text", "")).strip())
    if trust_band != "risky" and raw_rule and not _looks_like_giant_command_blob(raw_rule):
        return (raw_rule[:_MAX_INLINE_HINT_CHARS], trust_band, "summary")

    anchor = _coarse_gap_anchor(lesson)
    evidence = expected_evidence or "confirm missing requirement is closed"
    caution = f"CAUTION[{lesson_id[:8]}|{trust_band}]: focus on gap={anchor}. Verify with evidence: {evidence}"
    return (_squash_ws(caution)[:_MAX_INLINE_HINT_CHARS], trust_band, "summary")


def _safe_lesson_hint_text(
    *,
    lesson: Any,
    rule_text: str,
    max_chars: int = 320,
) -> str:
    """
    Backward-compatible safe hint API used by tests and older call sites.

    This delegates to the newer runtime hint renderer so we keep one safety
    policy path for both prompt artifacts and runtime injections.
    """
    raw_rule = str(rule_text or "")
    if any(marker in raw_rule for marker in _UNSAFE_HINT_MARKERS):
        return ""
    raw_compact = _squash_ws(raw_rule)
    if raw_compact and raw_compact.count(";") > 8:
        return ""

    hint, _, _ = _render_runtime_lesson_hint(
        lesson=lesson,
        use_placebo=False,
        task_id=str(getattr(lesson, "task_id", "")),
        domain=str(getattr(lesson, "domain", "")),
    )
    compact = _squash_ws(hint or rule_text)
    if not compact:
        return ""
    limit = max(64, int(max_chars))
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)] + "..."


def _format_v2_lesson_block(
    matches: list[Any],
    *,
    use_placebo: bool = False,
    task_id: str = "",
    domain: str = "",
) -> tuple[str, list[str]]:
    if not matches:
        return "", []
    lines = ["Memory V2 lessons (high-signal):"]
    lesson_ids: list[str] = []
    for match in matches:
        lesson = getattr(match, "lesson", None)
        score = getattr(match, "score", None)
        if lesson is None:
            continue
        lesson_id = str(getattr(lesson, "lesson_id", ""))
        lesson_ids.append(lesson_id)
        score_value = float(getattr(score, "score", 0.0) or 0.0) if score is not None else 0.0
        hint_text, _, _ = _render_runtime_lesson_hint(
            lesson=lesson,
            use_placebo=use_placebo,
            task_id=task_id,
            domain=domain,
        )
        lines.append(f"- ({score_value:.2f}) {hint_text}")
    return "\n".join(lines), [value for value in lesson_ids if value]


def _serialize_prerun_v2_matches(matches: list[Any]) -> list[dict[str, Any]]:
    """Store retriever-selected lessons in prompt artifacts as structured rows.

    This keeps observability machine-readable and avoids ambiguous placeholder
    keys (for example, dict key lists accidentally interpreted as lessons).
    """
    rows: list[dict[str, Any]] = []
    for match in matches:
        lesson = getattr(match, "lesson", None)
        score = getattr(match, "score", None)
        if lesson is None:
            continue
        rows.append(
            {
                "lesson_id": str(getattr(lesson, "lesson_id", "")),
                "status": str(getattr(lesson, "status", "")),
                "trust_band": _lesson_trust_band(lesson),
                "task_id": str(getattr(lesson, "task_id", "")),
                "domain": str(getattr(lesson, "domain", "")),
                "rule_text": str(getattr(lesson, "rule_text", "")),
                "reason_code": str(getattr(lesson, "reason_code", "")),
                "gap_type": str(getattr(lesson, "gap_type", "")),
                "gap_signature": str(getattr(lesson, "gap_signature", "")),
                "action_template": str(getattr(lesson, "action_template", "")),
                "expected_evidence": str(getattr(lesson, "expected_evidence", "")),
                "score": float(getattr(score, "score", 0.0) or 0.0) if score is not None else 0.0,
                "lane": str(getattr(match, "lane", "")),
            }
        )
    return rows


def _format_legacy_placebo_lesson_block(
    *,
    lessons: list[Any],
    lessons_loaded: int,
    task_id: str,
    domain: str,
) -> str:
    if lessons_loaded <= 0:
        return "No prior lessons loaded."
    lines = [
        "CRITICAL lessons from previous sessions — control placeholders (content hidden):",
    ]
    emitted = 0
    for lesson in lessons:
        if emitted >= lessons_loaded:
            break
        session_id = int(getattr(lesson, "session_id", 0) or 0)
        category = str(getattr(lesson, "category", "")).strip().lower() or "insight"
        lesson_text = str(getattr(lesson, "lesson", "")).strip()
        seed = f"{session_id}:{category}:{lesson_text[:48]}"
        lines.append(
            "- [control] "
            + _placebo_hint_for_lesson(
                lesson_id=f"legacy:{seed}",
                task_id=task_id,
                domain=domain,
            )
        )
        emitted += 1
    while emitted < lessons_loaded:
        lines.append(
            "- [control] "
            + _placebo_hint_for_lesson(
                lesson_id=f"legacy:pad:{emitted}",
                task_id=task_id,
                domain=domain,
            )
        )
        emitted += 1
    return "\n".join(lines)


def _has_promoted_v2_lesson_for_task(*, path: Path, task_id: str, domain: str) -> bool:
    normalized_domain = str(domain).strip().lower()
    for record in load_lesson_records(path):
        if str(getattr(record, "status", "")).strip().lower() != "promoted":
            continue
        if str(getattr(record, "task_id", "")).strip() != task_id:
            continue
        record_domain = str(getattr(record, "domain", "")).strip().lower()
        if record_domain and record_domain != normalized_domain:
            continue
        return True
    return False


def _select_high_signal_prerun_matches(
    *,
    matches: list[Any],
    task_id: str,
    domain: str,
    max_results: int = 4,
    min_score: float = 0.55,
) -> list[Any]:
    """
    Keep pre-run memory injection small and targeted.

    Why this exists:
    - pre-run lesson blobs can become noisy and dilute tool execution quality
    - task/domain exact matches should dominate broad historical hints
    """
    if not matches:
        return []

    def _is_dynamic_task(task_ref: str) -> bool:
        text = str(task_ref or "").strip().lower()
        # Telegram/OpenClaw natural-language tasks are materialized with a
        # dynamic id. These tasks rarely start with strong fingerprint/tag
        # anchors, so they need a softer fallback path to bootstrap retrieval.
        return text.startswith("openclaw_dynamic_") or text.startswith("dynamic_")

    def _has_structured_gap_fields(lesson_obj: Any) -> bool:
        return bool(
            str(getattr(lesson_obj, "reason_code", "")).strip()
            or str(getattr(lesson_obj, "gap_type", "")).strip()
            or str(getattr(lesson_obj, "gap_signature", "")).strip()
        )

    def _has_executable_shape(lesson_obj: Any) -> bool:
        return bool(
            str(getattr(lesson_obj, "action_template", "")).strip()
            and str(getattr(lesson_obj, "expected_evidence", "")).strip()
        )

    def _is_verifier_only_execution_lesson(lesson_obj: Any) -> bool:
        """
        Skip lessons that only tell the agent to re-run checks.

        Why:
        - these rows are useful as post-run diagnostics
        - they are harmful as pre-run memory because they crowd out real fixes
        - the failure pattern is: import/patch is broken, but memory says
          "run SELECT and compare expected rows" instead of fixing the import
        """
        rule_text = str(getattr(lesson_obj, "rule_text", "")).strip().lower()
        action_template = str(getattr(lesson_obj, "action_template", "")).strip().lower()
        if "run validator query and reconcile data exactly" in rule_text:
            return True
        if "expected_rows=" in action_template and "run_sqlite(sql=\"select" in action_template:
            return True
        return False

    def _is_over_broad_shell_action_template(lesson_obj: Any) -> bool:
        """
        Drop shell action templates that bundle too many commands.

        Why:
        - Broad "do everything at once" shell templates are brittle under tight
          step budgets and have been correlated with harmful activations.
        - Pre-run retrieval should prefer one focused corrective action.
        """
        lesson_domain = str(getattr(lesson_obj, "domain", "")).strip().lower()
        if lesson_domain and lesson_domain != "shell":
            return False
        action_template = str(getattr(lesson_obj, "action_template", "")).strip()
        if not action_template.lower().startswith("run_bash("):
            return False
        normalized = _squash_ws(action_template)
        delimiter_count = normalized.count(";") + normalized.count("&&") + normalized.count("||")
        if delimiter_count >= 3:
            return True
        if len(normalized) > 220 and delimiter_count >= 2:
            return True
        if "source_repo" in normalized and "target_repo" in normalized and delimiter_count >= 2:
            return True
        return False

    def _fallback_semantic_anchor(score_obj: Any) -> bool:
        # Keep fallback deterministic and conservative. We only consider
        # lessons that have at least minimal lexical/semantic overlap.
        text_sim = float(getattr(score_obj, "text_similarity", 0.0) or 0.0)
        sem_sim = float(getattr(score_obj, "semantic_similarity", 0.0) or 0.0)
        return text_sim >= 0.02 or sem_sim >= 0.10

    def _lesson_status_rank(lesson_obj: Any) -> int:
        # Pre-run memory should trust proven lessons first. Candidates are
        # still useful for cold start, but they should not crowd out promoted
        # signal when both exist.
        status = str(getattr(lesson_obj, "status", "")).strip().lower()
        if status == "promoted":
            return 0
        if status == "candidate":
            return 1
        return 2

    def _structured_prerun_family_key(lesson_obj: Any) -> str:
        # Use broad failure family, not exact signature, so one task does not
        # inject three near-identical "fix required query" recipes at once.
        reason = str(getattr(lesson_obj, "reason_code", "")).strip()
        gap_type = str(getattr(lesson_obj, "gap_type", "")).strip()
        if reason or gap_type:
            return f"rg:{reason}|{gap_type}"
        signature = str(getattr(lesson_obj, "gap_signature", "")).strip()
        return f"sig:{signature}" if signature else ""

    normalized_domain = str(domain).strip().lower()
    limit = max(0, int(max_results))
    threshold = float(min_score)
    selected: list[Any] = []
    seen_ids: set[str] = set()

    # Pass 1: exact task+domain matches with non-trivial score.
    for match in matches:
        lesson = getattr(match, "lesson", None)
        score = getattr(match, "score", None)
        if lesson is None or score is None:
            continue
        lesson_id = str(getattr(lesson, "lesson_id", "")).strip()
        if not lesson_id or lesson_id in seen_ids:
            continue
        if str(getattr(lesson, "task_id", "")).strip() != task_id:
            continue
        lesson_domain = str(getattr(lesson, "domain", "")).strip().lower()
        if lesson_domain and lesson_domain != normalized_domain:
            continue
        if float(getattr(score, "score", 0.0) or 0.0) < threshold:
            continue
        selected.append(match)
        seen_ids.add(lesson_id)
        if len(selected) >= limit:
            return selected

    # Pass 2: same-domain fallback for remaining slots.
    for match in matches:
        lesson = getattr(match, "lesson", None)
        score = getattr(match, "score", None)
        if lesson is None or score is None:
            continue
        lesson_id = str(getattr(lesson, "lesson_id", "")).strip()
        if not lesson_id or lesson_id in seen_ids:
            continue
        if str(getattr(lesson, "domain", "")).strip().lower() != normalized_domain:
            continue
        if float(getattr(score, "score", 0.0) or 0.0) < threshold:
            continue
        selected.append(match)
        seen_ids.add(lesson_id)
        if len(selected) >= limit:
            break

    if selected:
        return selected

    # Pass 3: exact task-id fallback for structured executable lessons.
    # Why this exists:
    # - strict thresholding can starve same-task memory on hard tasks
    # - structured lessons are already validated and safer than free-form text
    # - this applies to any task id, not only dynamic chat ids
    same_task_min_score = 0.05
    structured_same_task_candidates: list[Any] = []
    for match in matches:
        lesson = getattr(match, "lesson", None)
        score = getattr(match, "score", None)
        if lesson is None or score is None:
            continue
        lesson_id = str(getattr(lesson, "lesson_id", "")).strip()
        if not lesson_id or lesson_id in seen_ids:
            continue
        if str(getattr(lesson, "task_id", "")).strip() != task_id:
            continue
        lesson_domain = str(getattr(lesson, "domain", "")).strip().lower()
        if lesson_domain and lesson_domain != normalized_domain:
            continue
        if not _has_structured_gap_fields(lesson):
            continue
        if not _has_executable_shape(lesson):
            continue
        if _is_over_broad_shell_action_template(lesson):
            continue
        if _is_verifier_only_execution_lesson(lesson):
            continue
        if float(getattr(score, "score", 0.0) or 0.0) < same_task_min_score:
            continue
        structured_same_task_candidates.append(match)

    if structured_same_task_candidates:
        promoted_candidates = [
            match
            for match in structured_same_task_candidates
            if _lesson_status_rank(getattr(match, "lesson", None)) == 0
        ]
        candidate_pool = (
            promoted_candidates if promoted_candidates else structured_same_task_candidates
        )

        # Collapse multiple lessons from the same failure family into one
        # strongest row. This keeps pre-run context small and mirrors the
        # shell hotfix lane where one focused lesson helped more than a bundle.
        best_by_family: dict[str, Any] = {}
        ordered_family_keys: list[str] = []
        for match in candidate_pool:
            lesson = getattr(match, "lesson", None)
            if lesson is None:
                continue
            family_key = _structured_prerun_family_key(lesson) or str(
                getattr(lesson, "lesson_id", "")
            ).strip()
            if not family_key:
                continue
            current = best_by_family.get(family_key)
            if current is None:
                best_by_family[family_key] = match
                ordered_family_keys.append(family_key)
                continue
            current_lesson = getattr(current, "lesson", None)
            current_score = getattr(getattr(current, "score", None), "score", 0.0) or 0.0
            new_score = float(getattr(getattr(match, "score", None), "score", 0.0) or 0.0)
            current_rank = _lesson_status_rank(current_lesson)
            new_rank = _lesson_status_rank(lesson)
            if (new_rank, -new_score) < (current_rank, -current_score):
                best_by_family[family_key] = match

        structured_limit = min(limit, 2)
        for family_key in ordered_family_keys:
            match = best_by_family.get(family_key)
            if match is None:
                continue
            lesson = getattr(match, "lesson", None)
            lesson_id = str(getattr(lesson, "lesson_id", "")).strip()
            if not lesson_id or lesson_id in seen_ids:
                continue
            selected.append(match)
            seen_ids.add(lesson_id)
            if len(selected) >= structured_limit:
                break

    if selected or not _is_dynamic_task(task_id):
        return selected

    # Pass 4 (dynamic-task fallback): exact task-id matches with low scores.
    # Why this exists:
    # - dynamic tasks start without stable trigger fingerprints/tags
    # - strict threshold filtering can drop all lessons even after repeated
    #   failures on the same task_id
    # Guardrails:
    # - only for dynamic task ids
    # - only for lessons without structured gap signatures
    # - requires at least minimal semantic/lexical anchor
    dynamic_min_score = 0.05
    for match in matches:
        lesson = getattr(match, "lesson", None)
        score = getattr(match, "score", None)
        if lesson is None or score is None:
            continue
        lesson_id = str(getattr(lesson, "lesson_id", "")).strip()
        if not lesson_id or lesson_id in seen_ids:
            continue
        if str(getattr(lesson, "task_id", "")).strip() != task_id:
            continue
        lesson_domain = str(getattr(lesson, "domain", "")).strip().lower()
        if lesson_domain and lesson_domain != normalized_domain:
            continue
        if _has_structured_gap_fields(lesson):
            continue
        if float(getattr(score, "score", 0.0) or 0.0) < dynamic_min_score:
            continue
        if not _fallback_semantic_anchor(score):
            continue
        selected.append(match)
        seen_ids.add(lesson_id)
        if len(selected) >= limit:
            break

    if selected:
        return selected

    # Pass 5 (dynamic semantic backfill): same-domain/domainless legacy lessons.
    for match in matches:
        lesson = getattr(match, "lesson", None)
        score = getattr(match, "score", None)
        if lesson is None or score is None:
            continue
        lesson_id = str(getattr(lesson, "lesson_id", "")).strip()
        if not lesson_id or lesson_id in seen_ids:
            continue
        if _has_structured_gap_fields(lesson):
            continue
        lesson_domain = str(getattr(lesson, "domain", "")).strip().lower()
        if lesson_domain and lesson_domain != normalized_domain:
            continue
        if not _fallback_semantic_anchor(score):
            continue
        selected.append(match)
        seen_ids.add(lesson_id)
        if len(selected) >= limit:
            break

    return selected


def _gap_family_key_from_row(gap_row: dict[str, Any]) -> str:
    """Build a stable family key for one unresolved gap row."""
    signature = str(gap_row.get("gap_signature", "")).strip()
    if signature:
        return f"sig:{signature}"
    reason = str(gap_row.get("reason_code", "")).strip()
    gap_type = str(gap_row.get("gap_type", "")).strip()
    if reason or gap_type:
        return f"rg:{reason}|{gap_type}"
    detail = str(gap_row.get("detail", "")).strip()
    return f"detail:{detail}" if detail else ""


def _gap_family_key_from_lesson(lesson: Any) -> str:
    """Build a stable family key for one lesson row."""
    signature = str(getattr(lesson, "gap_signature", "")).strip()
    if signature:
        return f"sig:{signature}"
    reason = str(getattr(lesson, "reason_code", "")).strip()
    gap_type = str(getattr(lesson, "gap_type", "")).strip()
    if reason or gap_type:
        return f"rg:{reason}|{gap_type}"
    return ""


def _has_repo_init_gap(unresolved_gaps: list[dict[str, Any]]) -> bool:
    """Detect unresolved gaps that indicate repository init/setup is missing."""
    for row in unresolved_gaps:
        if not isinstance(row, dict):
            continue
        detail = str(row.get("detail", "")).lower()
        signature = str(row.get("gap_signature", "")).lower()
        payload = f"{detail} {signature}"
        if "git\\s+init" in payload:
            return True
    return False


def _is_variant_specific_patch_apply_hint(lesson: Any) -> bool:
    """
    Identify overly specific hotfix apply hints that are usually wrong for init gaps.

    We only suppress these when unresolved gaps are about repo init/setup.
    """
    rule_text = str(getattr(lesson, "rule_text", "")).lower()
    action_template = str(getattr(lesson, "action_template", "")).lower()
    payload = f"{rule_text}\n{action_template}"
    has_variant_patch = bool(re.search(r"hotfix_(alpha|beta|gamma)\.(patch|txt)", payload))
    mentions_apply = bool(re.search(r"\bgit\b[\s\S]{0,80}\bam\b", payload)) or "apply patch" in payload
    return has_variant_patch and mentions_apply


def _is_patch_apply_prereq_miss_for_error(*, lesson: Any, current_error_text: str) -> bool:
    """
    Suppress patch-apply lessons when current error indicates missing prerequisites.

    First-principles:
    - A `git am ../patch` repair is a late-stage action.
    - If current failure says spec/source artifact is missing, repeating `git am`
      is usually a dead-end and burns steps.
    """
    error_text = str(current_error_text or "").strip().lower()
    if not error_text:
        return False
    action_template = str(getattr(lesson, "action_template", "") or "").strip().lower()
    rule_text = str(getattr(lesson, "rule_text", "") or "").strip().lower()
    payload = f"{action_template}\n{rule_text}"
    mentions_patch_apply = bool(re.search(r"\bgit\b[\s\S]{0,80}\bam\b", payload))
    if not mentions_patch_apply:
        return False

    missing_markers = (
        "no such file or directory",
        "could not open",
        "pathspec",
        "filenotfounderror",
        "jsondecodeerror",
        "unbound variable",
        "spec not found",
        "variant_spec.json",
    )
    if not any(marker in error_text for marker in missing_markers):
        return False

    prereq_markers = (
        "source_repo",
        "target_repo",
        "hotfix_",
        "patch",
        "variant_spec",
    )
    return any(marker in error_text for marker in prereq_markers)


def _adaptive_gap_lesson_cap(
    *,
    unresolved_gaps: list[dict[str, Any]],
    min_cap: int = 1,
    max_cap: int = 3,
) -> int:
    """
    Set lesson injection cap from unresolved-gap diversity.

    First-principles:
    - one dominant gap => one focused lesson
    - multiple distinct gap families => allow up to three lessons
    """
    minimum = max(1, int(min_cap))
    maximum = max(minimum, int(max_cap))
    families = {
        key
        for key in (_gap_family_key_from_row(row) for row in unresolved_gaps if isinstance(row, dict))
        if key
    }
    if not families:
        return minimum
    return max(minimum, min(maximum, len(families)))


def _select_gap_targeted_matches(
    *,
    matches: list[Any],
    unresolved_gaps: list[dict[str, Any]],
    max_lessons: int,
    min_score: float = 0.25,
    current_error_text: str = "",
) -> list[Any]:
    """
    Keep retrieval focused: up to N lessons, one per gap family.

    Why:
    - prevents duplicate hints for the same unresolved blocker
    - avoids context flooding from many low-value lessons
    """
    if not matches:
        return []
    cap = max(1, int(max_lessons))
    threshold = float(min_score)
    unresolved_families = {
        key
        for key in (_gap_family_key_from_row(row) for row in unresolved_gaps if isinstance(row, dict))
        if key
    }
    has_repo_init_gap = _has_repo_init_gap(unresolved_gaps)
    selected: list[Any] = []
    seen_lesson_ids: set[str] = set()
    used_families: set[str] = set()
    for match in matches:
        lesson = getattr(match, "lesson", None)
        score = getattr(match, "score", None)
        if lesson is None:
            continue
        lesson_id = str(getattr(lesson, "lesson_id", "")).strip()
        if not lesson_id or lesson_id in seen_lesson_ids:
            continue
        score_value = float(getattr(score, "score", 0.0) or 0.0) if score is not None else 0.0
        if score_value < threshold:
            continue
        # Prevent a known bad pattern: when the unresolved blocker is repo init,
        # injecting variant-specific "git am hotfix_beta.patch" hints causes
        # the model to chase the wrong sub-problem.
        if has_repo_init_gap and _is_variant_specific_patch_apply_hint(lesson):
            continue
        # If current failure is a prerequisite miss, avoid late-stage patch
        # apply hints (`git am ...`) that cannot succeed yet.
        if _is_patch_apply_prereq_miss_for_error(lesson=lesson, current_error_text=current_error_text):
            continue
        family_key = _gap_family_key_from_lesson(lesson)
        if unresolved_families:
            if not family_key or family_key not in unresolved_families:
                continue
            if family_key in used_families:
                continue
            used_families.add(family_key)
        selected.append(match)
        seen_lesson_ids.add(lesson_id)
        if len(selected) >= cap:
            break
    if selected:
        return selected
    if unresolved_families:
        # Strict unresolved-gap mode should prefer no hint over wrong hint.
        return []
    # No explicit unresolved gap context available: fallback to top-ranked rows.
    return list(matches[:cap])
