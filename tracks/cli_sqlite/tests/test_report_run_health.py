from __future__ import annotations

import json

import pytest

from tracks.cli_sqlite.run_observability import append_run_ledger_entry
from tracks.cli_sqlite.scripts.report_run_health import load_recent_runs, summarize_run_health


def test_report_run_health_parser_and_summary(tmp_path) -> None:
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir(parents=True, exist_ok=True)

    append_run_ledger_entry(
        sessions_root=sessions_root,
        run_id="run-801-1000",
        session_id=801,
        task_id="aggregate_report",
        domain="gridtool",
        learn_mode="strict",
        started_at="2026-02-25T12:00:00Z",
        ended_at="2026-02-25T12:00:05Z",
        status="failed",
        error_summary="network error",
    )
    append_run_ledger_entry(
        sessions_root=sessions_root,
        run_id="run-802-1000",
        session_id=802,
        task_id="aggregate_report",
        domain="gridtool",
        learn_mode="strict",
        started_at="2026-02-25T12:01:00Z",
        ended_at="2026-02-25T12:01:05Z",
        status="completed",
        error_summary="",
    )
    append_run_ledger_entry(
        sessions_root=sessions_root,
        run_id="run-803-1000",
        session_id=803,
        task_id="aggregate_report",
        domain="gridtool",
        learn_mode="strict",
        started_at="2026-02-25T12:02:00Z",
        ended_at="2026-02-25T12:02:05Z",
        status="timed_out",
        error_summary="timeout",
    )

    (sessions_root / "session-801").mkdir(parents=True, exist_ok=True)
    (sessions_root / "session-802").mkdir(parents=True, exist_ok=True)
    (sessions_root / "session-803").mkdir(parents=True, exist_ok=True)
    (sessions_root / "session-801" / "metrics.json").write_text(
        json.dumps(
            {
                "eval_passed": False,
                "v2_lessons_generated": 0,
                "v2_retrieval_help_ratio": 0.0,
                "v2_fingerprint_recurrence_before": 3,
                "v2_fingerprint_recurrence_after": 2,
                "contract_gap_unresolved_count_prestop": 2,
                "contract_gap_unresolved_count_final": 1,
                "contract_gap_retry_triggered": 1,
                "contract_gap_retry_attempts": 1,
                "v2_transfer_lane_activations": 1,
                "v2_transfer_retrieval_enabled": True,
            }
        ),
        encoding="utf-8",
    )
    (sessions_root / "session-802" / "metrics.json").write_text(
        json.dumps(
            {
                "eval_passed": True,
                "v2_lessons_generated": 2,
                "v2_retrieval_help_ratio": 0.5,
                "v2_fingerprint_recurrence_before": 2,
                "v2_fingerprint_recurrence_after": 1,
                "contract_gap_unresolved_count_prestop": 1,
                "contract_gap_unresolved_count_final": 0,
                "contract_gap_retry_triggered": 1,
                "contract_gap_retry_attempts": 1,
                "v2_transfer_lane_activations": 2,
                "v2_transfer_retrieval_enabled": True,
            }
        ),
        encoding="utf-8",
    )
    (sessions_root / "session-803" / "metrics.json").write_text(
        json.dumps(
            {
                "eval_passed": False,
                "v2_lessons_generated": 1,
                "v2_retrieval_help_ratio": 0.9,
                "v2_fingerprint_recurrence_before": 1,
                "v2_fingerprint_recurrence_after": 2,
                "v2_transfer_lane_activations": 0,
                "v2_transfer_retrieval_enabled": True,
            }
        ),
        encoding="utf-8",
    )

    rows = load_recent_runs(sessions_root=sessions_root, last_n=10)
    summary = summarize_run_health(rows)
    assert summary["runs"] == 3
    assert summary["fail_rate"] == 1 / 3
    assert summary["cancel_rate"] == 0.0
    assert summary["timeout_rate"] == 1 / 3
    assert summary["lesson_writes_total"] == 3
    assert summary["lesson_write_runs"] == 2
    assert summary["retrieval_help_ratio_mean"] == (0.0 + 0.5 + 0.9) / 3
    assert summary["retrieval_help_trend_delta"] == 0.9
    assert summary["first_success_session"] == 802
    assert summary["first_success_run_index"] == 2
    assert summary["repeated_fingerprint_decay_proxy_mean"] == pytest.approx((1.0 + 1.0 - 1.0) / 3.0)
    assert summary["repeated_fingerprint_decay_proxy_positive_rate"] == pytest.approx(2.0 / 3.0)
    assert summary["repeated_fingerprint_decay_proxy_net"] == pytest.approx(1.0)
    assert summary["gap_signal_runs"] == 2
    assert summary["gap_resolution_runs"] == 1
    assert summary["gap_resolution_rate"] == pytest.approx(0.5)
    assert summary["time_to_gap_resolution_proxy_runs"] == 2
    assert summary["time_to_gap_resolution_proxy_s"] == pytest.approx(65.0)
    assert summary["transfer_active_runs"] == 2
    assert summary["transfer_hit_runs"] == 1
    assert summary["transfer_hit_rate_proxy"] == pytest.approx(0.5)


def test_report_run_health_first_success_falls_back_to_completed_status(tmp_path) -> None:
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir(parents=True, exist_ok=True)

    append_run_ledger_entry(
        sessions_root=sessions_root,
        run_id="run-901-1000",
        session_id=901,
        task_id="aggregate_report",
        domain="gridtool",
        learn_mode="strict",
        started_at="2026-02-25T12:00:00Z",
        ended_at="2026-02-25T12:00:05Z",
        status="failed",
        error_summary="error",
    )
    append_run_ledger_entry(
        sessions_root=sessions_root,
        run_id="run-902-1000",
        session_id=902,
        task_id="aggregate_report",
        domain="gridtool",
        learn_mode="strict",
        started_at="2026-02-25T12:01:00Z",
        ended_at="2026-02-25T12:01:05Z",
        status="completed",
        error_summary="",
    )

    # Deliberately omit metrics.json for session-902 to exercise backward
    # compatibility with historical runs that only had ledger status.
    (sessions_root / "session-901").mkdir(parents=True, exist_ok=True)
    (sessions_root / "session-901" / "metrics.json").write_text(
        json.dumps({"eval_passed": False}),
        encoding="utf-8",
    )

    rows = load_recent_runs(sessions_root=sessions_root, last_n=10)
    summary = summarize_run_health(rows)
    assert summary["first_success_session"] == 902
    assert summary["first_success_run_index"] == 2
