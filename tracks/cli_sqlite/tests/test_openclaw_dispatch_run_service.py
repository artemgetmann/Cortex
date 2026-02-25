from __future__ import annotations

from integrations import openclaw_agi_dispatch as dispatch
from tracks.cli_sqlite import run_service


def _run_record(*, run_id: str, status: str) -> run_service.RunRecord:
    return run_service.RunRecord(
        run_id=run_id,
        session_id=8801,
        task_id="aggregate_report",
        domain="gridtool",
        status=status,
        created_at_epoch_s=1.0,
        updated_at_epoch_s=2.0,
        started_at_epoch_s=1.0,
    )


def test_build_plan_parses_cancel_with_run_id() -> None:
    plan = dispatch._build_plan(
        "/cancel run_id=run_1730000000000_00000042",
        chat_scope="tg-1",
        default_domain="shell",
    )
    assert plan.mode == "cancel"
    assert plan.run_id == "run_1730000000000_00000042"


def test_status_payload_exposes_active_runs(monkeypatch) -> None:
    monkeypatch.setattr(dispatch.run_service, "list_active", lambda: [_run_record(run_id="run_1", status="running")])
    monkeypatch.setattr(
        dispatch.run_service,
        "get_run",
        lambda run_id: _run_record(run_id=run_id, status="running"),
    )
    payload = dispatch._status_payload(chat_scope="tg-1", run_id="run_1")
    assert payload["mode"] == "status"
    assert payload["run"]["run_id"] == "run_1"
    assert payload["active_runs"][0]["run_id"] == "run_1"


def test_cancel_payload_calls_run_service(monkeypatch) -> None:
    monkeypatch.setattr(
        dispatch.run_service,
        "cancel_run",
        lambda run_id, reason=None: _run_record(run_id=run_id, status=run_service.STATUS_CANCEL_REQUESTED),
    )
    payload, rc = dispatch._cancel_payload(run_id="run_2")
    assert rc == 0
    assert payload["ok"] is True
    assert payload["run"]["status"] == run_service.STATUS_CANCEL_REQUESTED
