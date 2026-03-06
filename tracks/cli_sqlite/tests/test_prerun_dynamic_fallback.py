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
    action_template: str = "",
    expected_evidence: str = "",
    status: str = "candidate",
):
    lesson = SimpleNamespace(
        lesson_id=lesson_id,
        task_id=task_id,
        domain=domain,
        reason_code=reason_code,
        gap_type=gap_type,
        gap_signature=gap_signature,
        action_template=action_template,
        expected_evidence=expected_evidence,
        status=status,
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


def test_non_dynamic_task_allows_structured_executable_same_task_fallback() -> None:
    matches = [
        _match(
            lesson_id="lsn_structured_exec",
            task_id="shell_git_transfer_hotfix_hard",
            domain="shell",
            score=0.12,
            text_similarity=0.01,
            reason_code="missing_required_event_pattern",
            gap_type="required_event_pattern",
            gap_signature="missing_required_event_pattern|required_event_pattern|(?is)git\\s+am\\s+\\.\\./hotfix_gamma.patch",
            action_template='run_bash(command="git -C target_repo am ../hotfix_gamma.patch")',
            expected_evidence="missing_required_event_pattern|required_event_pattern|(?is)git\\s+am\\s+\\.\\./hotfix_gamma.patch",
        )
    ]
    selected = _select_high_signal_prerun_matches(
        matches=matches,
        task_id="shell_git_transfer_hotfix_hard",
        domain="shell",
        max_results=4,
        min_score=0.55,
    )
    assert [m.lesson.lesson_id for m in selected] == ["lsn_structured_exec"]


def test_same_task_structured_fallback_prefers_promoted_and_dedupes_family() -> None:
    matches = [
        _match(
            lesson_id="lsn_candidate_query_a",
            task_id="incremental_reconcile",
            domain="sqlite",
            score=0.18,
            text_similarity=0.02,
            reason_code="required_query_mismatch",
            gap_type="required_query",
            gap_signature="required_query_mismatch|required_query|ledger_aggregate",
            action_template='run_sqlite(sql="SELECT 1")',
            expected_evidence="ledger aggregate present",
            status="candidate",
        ),
        _match(
            lesson_id="lsn_promoted_query_b",
            task_id="incremental_reconcile",
            domain="sqlite",
            score=0.16,
            text_similarity=0.02,
            reason_code="required_query_mismatch",
            gap_type="required_query",
            gap_signature="required_query_mismatch|required_query|reject_count",
            action_template='run_sqlite(sql="SELECT 2")',
            expected_evidence="reject count present",
            status="promoted",
        ),
        _match(
            lesson_id="lsn_candidate_error_budget",
            task_id="incremental_reconcile",
            domain="sqlite",
            score=0.15,
            text_similarity=0.02,
            reason_code="too_many_errors",
            gap_type="error_budget",
            gap_signature="too_many_errors|error_budget|max=1",
            action_template='run_sqlite(sql="SELECT 3")',
            expected_evidence="lower error count",
            status="candidate",
        ),
    ]
    selected = _select_high_signal_prerun_matches(
        matches=matches,
        task_id="incremental_reconcile",
        domain="sqlite",
        max_results=4,
        min_score=0.55,
    )
    assert [m.lesson.lesson_id for m in selected] == ["lsn_promoted_query_b"]


def test_same_task_structured_fallback_caps_to_two_families_without_promoted() -> None:
    matches = [
        _match(
            lesson_id="lsn_query_best",
            task_id="incremental_reconcile",
            domain="sqlite",
            score=0.18,
            text_similarity=0.02,
            reason_code="required_query_mismatch",
            gap_type="required_query",
            gap_signature="required_query_mismatch|required_query|ledger_aggregate",
            action_template='run_sqlite(sql="SELECT 1")',
            expected_evidence="ledger aggregate present",
        ),
        _match(
            lesson_id="lsn_query_dup",
            task_id="incremental_reconcile",
            domain="sqlite",
            score=0.12,
            text_similarity=0.02,
            reason_code="required_query_mismatch",
            gap_type="required_query",
            gap_signature="required_query_mismatch|required_query|reject_count",
            action_template='run_sqlite(sql="SELECT 2")',
            expected_evidence="reject count present",
        ),
        _match(
            lesson_id="lsn_error_budget",
            task_id="incremental_reconcile",
            domain="sqlite",
            score=0.17,
            text_similarity=0.02,
            reason_code="too_many_errors",
            gap_type="error_budget",
            gap_signature="too_many_errors|error_budget|max=1",
            action_template='run_sqlite(sql="SELECT 3")',
            expected_evidence="lower error count",
        ),
        _match(
            lesson_id="lsn_pattern",
            task_id="incremental_reconcile",
            domain="sqlite",
            score=0.16,
            text_similarity=0.02,
            reason_code="missing_required_pattern",
            gap_type="required_sql_pattern",
            gap_signature="missing_required_pattern|required_sql_pattern|begin",
            action_template='run_sqlite(sql="BEGIN IMMEDIATE; SELECT 4; COMMIT;")',
            expected_evidence="explicit transaction",
        ),
    ]
    selected = _select_high_signal_prerun_matches(
        matches=matches,
        task_id="incremental_reconcile",
        domain="sqlite",
        max_results=4,
        min_score=0.55,
    )
    assert [m.lesson.lesson_id for m in selected] == ["lsn_query_best", "lsn_error_budget"]
