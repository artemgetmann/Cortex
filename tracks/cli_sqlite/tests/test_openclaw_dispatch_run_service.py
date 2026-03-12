from __future__ import annotations

from pathlib import Path

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


def _run_record_with_session(*, run_id: str, status: str, session_id: int) -> run_service.RunRecord:
    return run_service.RunRecord(
        run_id=run_id,
        session_id=session_id,
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


def test_build_plan_parses_run_status_with_progress_controls() -> None:
    plan = dispatch._build_plan(
        "/run-status run_id=run_1730000000000_00000042 progress=on limit=4",
        chat_scope="tg-1",
        default_domain="shell",
    )
    assert plan.mode == "status"
    assert plan.run_id == "run_1730000000000_00000042"
    assert plan.progress is True
    assert plan.progress_limit == 4


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


def test_coerce_lifecycle_event_preserves_followup_metadata() -> None:
    event = dispatch._coerce_lifecycle_event(
        {
            "ts": 10.0,
            "event": "followup",
            "text": "retry with strict verifier",
            "source": "transport:tg-1",
            "run_id": "run_1",
        }
    )
    assert event is not None
    assert event["event"] == "followup"
    assert event["text"] == "retry with strict verifier"
    assert event["source"] == "transport:tg-1"


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


def test_followup_payload_reports_missing_run_id(monkeypatch) -> None:
    monkeypatch.setattr(
        dispatch.run_service,
        "append_followup",
        lambda run_id, text, source, ts: None,
    )
    payload, rc = dispatch._followup_payload(
        run_id="run_missing",
        followup_text="retry with a stricter verifier",
        chat_scope="tg-1",
    )
    assert rc == 1
    assert payload["ok"] is False
    assert payload["error"] == "run_id not found"


def test_latest_lifecycle_events_uses_run_service_resolved_path(monkeypatch) -> None:
    expected_path = Path("/tmp/cortex_custom_lifecycle.jsonl")
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        dispatch.run_service,
        "resolve_lifecycle_path",
        lambda: expected_path,
    )

    def _fake_list_events(run_id: str, *, max_events: int, lifecycle_path: Path):
        captured["run_id"] = run_id
        captured["max_events"] = max_events
        captured["path"] = lifecycle_path
        return [{"ts": 10.0, "event": "started", "run_id": run_id}]

    monkeypatch.setattr(dispatch.run_service, "list_events", _fake_list_events)
    events = dispatch._latest_lifecycle_events(run_id="run_1", limit=4)
    assert len(events) == 1
    assert events[0]["event"] == "started"
    assert captured["run_id"] == "run_1"
    assert captured["max_events"] == 4
    assert captured["path"] == expected_path


def test_latest_lifecycle_events_falls_back_to_session_id(monkeypatch, tmp_path: Path) -> None:
    lifecycle_path = tmp_path / "run_lifecycle.jsonl"
    lifecycle_path.write_text(
        "\n".join(
            [
                '{"ts": 1.0, "run_id": "run-8801-1", "session_id": 8801, "event": "started"}',
                '{"ts": 2.0, "run_id": "run-8801-1", "session_id": 8801, "event": "step", "step": 2, "trigger": "tool:run_bash:ok"}',
                '{"ts": 3.0, "run_id": "run-9999-1", "session_id": 9999, "event": "step", "step": 9}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(dispatch.run_service, "resolve_lifecycle_path", lambda: lifecycle_path)
    monkeypatch.setattr(
        dispatch.run_service,
        "list_events",
        lambda run_id, *, max_events, lifecycle_path: [],
    )
    events = dispatch._latest_lifecycle_events(
        run_id="run_1773000000000_00000001",
        limit=4,
        session_id=8801,
    )
    assert len(events) == 2
    assert events[-1]["event"] == "step"
    assert events[-1]["trigger"] == "tool:run_bash:ok"


def test_status_payload_progress_mode_includes_lifecycle_events(monkeypatch) -> None:
    monkeypatch.setattr(dispatch.run_service, "list_active", lambda: [])
    monkeypatch.setattr(
        dispatch.run_service,
        "get_run",
        lambda run_id: _run_record_with_session(run_id=run_id, status="running", session_id=8801),
    )
    monkeypatch.setattr(
        dispatch,
        "_latest_lifecycle_events",
        lambda run_id, limit, session_id=None: [{"ts": 11.0, "event": "step", "run_id": run_id}],
    )
    payload = dispatch._status_payload(
        chat_scope="tg-1",
        run_id="run_1",
        include_progress=True,
        progress_limit=5,
    )
    assert payload["progress_mode"] is True
    assert payload["progress_limit"] == 5
    assert len(payload["lifecycle_events"]) == 1
