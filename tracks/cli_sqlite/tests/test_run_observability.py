from __future__ import annotations

from tracks.cli_sqlite.run_observability import (
    append_lifecycle_event,
    append_run_ledger_entry,
    read_jsonl_rows,
    run_ledger_path,
    run_lifecycle_path,
)


def test_run_ledger_append_schema(tmp_path) -> None:
    sessions_root = tmp_path / "sessions"
    append_run_ledger_entry(
        sessions_root=sessions_root,
        run_id="run-701-1000",
        session_id=701,
        task_id="aggregate_report",
        domain="gridtool",
        learn_mode="strict",
        started_at="2026-02-25T12:00:00Z",
        ended_at="2026-02-25T12:00:10Z",
        status="completed",
        error_summary="",
    )

    rows = read_jsonl_rows(run_ledger_path(sessions_root=sessions_root))
    assert len(rows) == 1
    row = rows[0]
    assert set(row.keys()) == {
        "run_id",
        "session_id",
        "task_id",
        "domain",
        "learn_mode",
        "started_at",
        "ended_at",
        "status",
        "error_summary",
    }
    assert row["run_id"] == "run-701-1000"
    assert row["session_id"] == 701
    assert row["task_id"] == "aggregate_report"
    assert row["domain"] == "gridtool"
    assert row["learn_mode"] == "strict"
    assert row["status"] == "completed"


def test_lifecycle_append_schema(tmp_path) -> None:
    sessions_root = tmp_path / "sessions"
    append_lifecycle_event(
        sessions_root=sessions_root,
        run_id="run-702-1000",
        session_id=702,
        task_id="aggregate_report",
        domain="gridtool",
        learn_mode="strict",
        event="step",
        step=3,
    )
    append_lifecycle_event(
        sessions_root=sessions_root,
        run_id="run-702-1000",
        session_id=702,
        task_id="aggregate_report",
        domain="gridtool",
        learn_mode="strict",
        event="contract_gap_retry",
        step=3,
        trigger="step_cap",
    )

    rows = read_jsonl_rows(run_lifecycle_path(sessions_root=sessions_root))
    assert len(rows) == 2
    assert rows[0]["event"] == "step"
    assert rows[0]["step"] == 3
    assert rows[1]["event"] == "contract_gap_retry"
    assert rows[1]["trigger"] == "step_cap"
    assert rows[1]["session_id"] == 702
