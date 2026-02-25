from __future__ import annotations

import json

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
        json.dumps({"v2_lessons_generated": 0, "v2_retrieval_help_ratio": 0.0}),
        encoding="utf-8",
    )
    (sessions_root / "session-802" / "metrics.json").write_text(
        json.dumps({"v2_lessons_generated": 2, "v2_retrieval_help_ratio": 0.5}),
        encoding="utf-8",
    )
    (sessions_root / "session-803" / "metrics.json").write_text(
        json.dumps({"v2_lessons_generated": 1, "v2_retrieval_help_ratio": 0.9}),
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
