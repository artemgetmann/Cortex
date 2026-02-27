from __future__ import annotations

from types import SimpleNamespace

from tracks.cli_sqlite.agent_cli import _select_high_signal_prerun_matches


def _match(
    *,
    lesson_id: str,
    task_id: str,
    domain: str,
    score: float,
    text_similarity: float,
    semantic_similarity: float = 0.0,
    reason_code: str = "",
    gap_type: str = "",
    gap_signature: str = "",
):
    lesson = SimpleNamespace(
        lesson_id=lesson_id,
        task_id=task_id,
        domain=domain,
        reason_code=reason_code,
        gap_type=gap_type,
        gap_signature=gap_signature,
    )
    retrieval_score = SimpleNamespace(
        score=score,
        text_similarity=text_similarity,
        semantic_similarity=semantic_similarity,
    )
    return SimpleNamespace(lesson=lesson, score=retrieval_score)


def test_dynamic_task_allows_low_signal_exact_task_fallback() -> None:
    matches = [
        # Higher score, but wrong task id.
        _match(
            lesson_id="lsn_other",
            task_id="incremental_reconcile",
            domain="sqlite",
            score=0.14,
            text_similarity=0.11,
        ),
        # Same dynamic task id, domainless, low score.
        _match(
            lesson_id="lsn_dynamic",
            task_id="openclaw_dynamic_chat_sqlite_abc123",
            domain="",
            score=0.09,
            text_similarity=0.08,
        ),
    ]
    selected = _select_high_signal_prerun_matches(
        matches=matches,
        task_id="openclaw_dynamic_chat_sqlite_abc123",
        domain="sqlite",
        max_results=4,
        min_score=0.55,
    )
    assert [m.lesson.lesson_id for m in selected] == ["lsn_dynamic"]


def test_non_dynamic_task_keeps_strict_threshold_behavior() -> None:
    matches = [
        _match(
            lesson_id="lsn_low",
            task_id="incremental_reconcile",
            domain="sqlite",
            score=0.11,
            text_similarity=0.09,
        )
    ]
    selected = _select_high_signal_prerun_matches(
        matches=matches,
        task_id="incremental_reconcile",
        domain="sqlite",
        max_results=4,
        min_score=0.55,
    )
    assert selected == []


def test_dynamic_fallback_excludes_structured_gap_lessons() -> None:
    matches = [
        _match(
            lesson_id="lsn_structured",
            task_id="openclaw_dynamic_chat_sqlite_def456",
            domain="",
            score=0.10,
            text_similarity=0.20,
            reason_code="missing_required_query",
            gap_type="required_query",
            gap_signature="missing_required_query|required_query|foo",
        ),
        _match(
            lesson_id="lsn_unstructured",
            task_id="openclaw_dynamic_chat_sqlite_def456",
            domain="",
            score=0.10,
            text_similarity=0.06,
        ),
    ]
    selected = _select_high_signal_prerun_matches(
        matches=matches,
        task_id="openclaw_dynamic_chat_sqlite_def456",
        domain="sqlite",
        max_results=4,
        min_score=0.55,
    )
    assert [m.lesson.lesson_id for m in selected] == ["lsn_unstructured"]
