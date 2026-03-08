from __future__ import annotations

import hashlib
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


def _placebo_hint_for_lesson(*, lesson_id: str, task_id: str, domain: str) -> str:
    token = f"{domain}|{task_id}|{lesson_id}".encode("utf-8", "ignore")
    digest = hashlib.sha256(token).hexdigest()
    idx = int(digest[:8], 16) % len(_PLACEBO_HINT_BANK)
    return f"PLACEBO_CONTROL[{digest[:6]}]: {_PLACEBO_HINT_BANK[idx]}"


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
        if use_placebo:
            rule_text = _placebo_hint_for_lesson(lesson_id=lesson_id, task_id=task_id, domain=domain)
        else:
            # Prefer structured lesson fields over raw rule_text because the
            # stored rule can be long and clipped. For execution memory we want
            # the minimal actionable core, not a half-truncated paragraph.
            gap_signature = str(getattr(lesson, "gap_signature", "")).strip()
            action_template = str(getattr(lesson, "action_template", "")).strip()
            expected_evidence = str(getattr(lesson, "expected_evidence", "")).strip()
            if gap_signature and action_template and expected_evidence:
                rule_text = (
                    f"WHEN gap_signature={gap_signature}: "
                    f"{action_template} EXPECT: {expected_evidence}"
                )
            else:
                rule_text = str(getattr(lesson, "rule_text", ""))
        lines.append(f"- ({score_value:.2f}) {rule_text}")
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
