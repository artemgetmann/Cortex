from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from tracks.cli_sqlite.lesson_store_v2 import LessonRecord, load_lesson_records


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _tokenize(text: str) -> set[str]:
    normalized = "".join(ch.lower() if ch.isalnum() else " " for ch in str(text))
    return {token for token in normalized.split() if token}


def _jaccard(a: str, b: str) -> float:
    ta = _tokenize(a)
    tb = _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / float(len(ta | tb))


def _fingerprint_match(query_fingerprint: str, lesson: LessonRecord) -> float:
    if not query_fingerprint:
        return 0.0
    if query_fingerprint in lesson.trigger_fingerprints:
        return 1.0
    # Prefix-level similarity still helps when hash truncation differs.
    for fp in lesson.trigger_fingerprints:
        if query_fingerprint[:10] and fp.startswith(query_fingerprint[:10]):
            return 0.7
    return 0.0


def _tag_overlap(query_tags: set[str], lesson_tags: set[str]) -> float:
    if not query_tags or not lesson_tags:
        return 0.0
    return len(query_tags & lesson_tags) / float(len(query_tags | lesson_tags))


def _recency_score(iso_ts: str) -> float:
    try:
        ts = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    now = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - ts).total_seconds() / 86400.0)
    # 14-day half-life keeps fresh lessons relevant without discarding history.
    return _clamp(1.0 / (1.0 + (age_days / 14.0)), 0.0, 1.0)


@dataclass(frozen=True)
class RetrievalScore:
    lesson_id: str
    score: float
    fingerprint_match: float
    tag_overlap: float
    text_similarity: float
    reliability: float
    recency: float


@dataclass(frozen=True)
class RetrievalMatch:
    lesson: LessonRecord
    score: RetrievalScore


@dataclass(frozen=True)
class RetrievalConfig:
    max_results: int = 8
    max_per_source_session: int = 2
    max_per_tag_bucket: int = 3


def _is_active(record: LessonRecord) -> bool:
    return record.status not in {"suppressed", "archived"}


def _build_score(
    *,
    lesson: LessonRecord,
    query_fingerprint: str,
    query_tags: set[str],
    query_text: str,
) -> RetrievalScore:
    fingerprint = _fingerprint_match(query_fingerprint, lesson)
    tags = _tag_overlap(query_tags, set(lesson.tags))
    similarity = _jaccard(query_text, lesson.rule_text)
    reliability = _clamp(lesson.reliability, 0.0, 1.0)
    recency = _recency_score(lesson.updated_at)
    total = (
        (0.40 * fingerprint)
        + (0.25 * tags)
        + (0.20 * similarity)
        + (0.10 * reliability)
        + (0.05 * recency)
    )
    return RetrievalScore(
        lesson_id=lesson.lesson_id,
        score=total,
        fingerprint_match=fingerprint,
        tag_overlap=tags,
        text_similarity=similarity,
        reliability=reliability,
        recency=recency,
    )


def _conflict_loser(
    kept: RetrievalMatch,
    challenger: RetrievalMatch,
) -> bool:
    """
    Return True if challenger should lose conflict resolution.

    Winner selection is deterministic: higher reliability first, then fresher
    evidence, then the computed retrieval score.
    """
    if challenger.lesson.reliability != kept.lesson.reliability:
        return challenger.lesson.reliability < kept.lesson.reliability
    if challenger.lesson.updated_at != kept.lesson.updated_at:
        return challenger.lesson.updated_at < kept.lesson.updated_at
    return challenger.score.score <= kept.score.score


def _select_with_guards(
    *,
    ranked: Sequence[RetrievalMatch],
    config: RetrievalConfig,
) -> tuple[list[RetrievalMatch], list[str]]:
    selected: list[RetrievalMatch] = []
    conflict_losers: list[str] = []
    per_session: dict[int, int] = {}
    per_tag_bucket: dict[str, int] = {}

    for match in ranked:
        lesson = match.lesson
        source_session = lesson.source_session_ids[-1] if lesson.source_session_ids else 0
        if source_session > 0 and per_session.get(source_session, 0) >= config.max_per_source_session:
            continue

        bucket = lesson.tags[0] if lesson.tags else "generic"
        if per_tag_bucket.get(bucket, 0) >= config.max_per_tag_bucket:
            continue

        conflict_with_idx = None
        for idx, chosen in enumerate(selected):
            if lesson.lesson_id in chosen.lesson.conflict_lesson_ids or chosen.lesson.lesson_id in lesson.conflict_lesson_ids:
                conflict_with_idx = idx
                break

        if conflict_with_idx is not None:
            chosen = selected[conflict_with_idx]
            if _conflict_loser(chosen, match):
                conflict_losers.append(lesson.lesson_id)
                continue
            conflict_losers.append(chosen.lesson.lesson_id)
            selected[conflict_with_idx] = match
            continue

        selected.append(match)
        if source_session > 0:
            per_session[source_session] = per_session.get(source_session, 0) + 1
        per_tag_bucket[bucket] = per_tag_bucket.get(bucket, 0) + 1

        if len(selected) >= config.max_results:
            break

    return selected, conflict_losers


def retrieve_lessons(
    *,
    records: Sequence[LessonRecord],
    query_text: str,
    query_fingerprint: str = "",
    query_tags: Sequence[str] = (),
    config: RetrievalConfig | None = None,
) -> tuple[list[RetrievalMatch], list[str]]:
    active = [record for record in records if _is_active(record)]
    query_tag_set = {str(tag).strip() for tag in query_tags if str(tag).strip()}
    ranked: list[RetrievalMatch] = []
    for lesson in active:
        score = _build_score(
            lesson=lesson,
            query_fingerprint=query_fingerprint,
            query_tags=query_tag_set,
            query_text=query_text,
        )
        if score.score <= 0:
            continue
        ranked.append(RetrievalMatch(lesson=lesson, score=score))
    ranked.sort(
        key=lambda row: (
            row.score.score,
            row.lesson.reliability,
            row.lesson.updated_at,
        ),
        reverse=True,
    )
    effective_config = config or RetrievalConfig()
    return _select_with_guards(ranked=ranked, config=effective_config)


def retrieve_pre_run(
    *,
    path: Path,
    task_id: str,
    domain: str,
    task_text: str,
    recent_fingerprints: Sequence[str] = (),
    query_tags: Sequence[str] = (),
    max_results: int = 8,
) -> tuple[list[RetrievalMatch], list[str]]:
    """Pre-run retrieval using intent context and recent fingerprints."""
    records = load_lesson_records(path)
    scoped = [row for row in records if (not row.task_id or row.task_id == task_id) or (row.domain and row.domain == domain)]
    primary_fingerprint = recent_fingerprints[0] if recent_fingerprints else ""
    return retrieve_lessons(
        records=scoped,
        query_text=task_text,
        query_fingerprint=primary_fingerprint,
        query_tags=query_tags,
        config=RetrievalConfig(max_results=max_results),
    )


def retrieve_on_error(
    *,
    path: Path,
    error_text: str,
    fingerprint: str,
    query_tags: Sequence[str] = (),
    max_results: int = 3,
) -> tuple[list[RetrievalMatch], list[str]]:
    """On-error retrieval prioritizing exact fingerprint matches."""
    records = load_lesson_records(path)
    return retrieve_lessons(
        records=records,
        query_text=error_text,
        query_fingerprint=fingerprint,
        query_tags=query_tags,
        config=RetrievalConfig(max_results=max_results),
    )


__all__ = [
    "RetrievalConfig",
    "RetrievalMatch",
    "RetrievalScore",
    "retrieve_lessons",
    "retrieve_on_error",
    "retrieve_pre_run",
]
