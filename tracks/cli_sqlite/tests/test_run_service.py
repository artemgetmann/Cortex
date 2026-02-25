from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tracks.cli_sqlite import run_service
from tracks.cli_sqlite.scripts import run_cli_agent as run_cli_agent_script


def test_run_id_generation_is_unique(tmp_path: Path) -> None:
    state_path = tmp_path / "run_service_state.json"
    ids = {run_service.generate_run_id(state_path=state_path) for _ in range(64)}
    assert len(ids) == 64
    assert all(run_id.startswith("run_") for run_id in ids)


def test_run_status_transitions_to_completed(tmp_path: Path) -> None:
    state_path = tmp_path / "run_service_state.json"
    started = run_service.start_run(
        task_id="aggregate_report",
        domain="gridtool",
        session_id=9101,
        state_path=state_path,
    )
    assert started.status == run_service.STATUS_RUNNING

    heartbeat = run_service.mark_heartbeat(started.run_id, last_step=3, state_path=state_path)
    assert heartbeat is not None
    assert heartbeat.last_step == 3

    finished = run_service.update_run(
        started.run_id,
        status=run_service.STATUS_COMPLETED,
        result={"eval_passed": True},
        state_path=state_path,
    )
    assert finished is not None
    assert finished.status == run_service.STATUS_COMPLETED
    assert finished.finished_at_epoch_s is not None
    assert run_service.list_active(state_path=state_path) == []


def test_cancel_state_marks_request_and_terminal_cancelled(tmp_path: Path) -> None:
    state_path = tmp_path / "run_service_state.json"
    started = run_service.start_run(
        task_id="shell_git_transfer_hotfix",
        domain="shell",
        session_id=9201,
        state_path=state_path,
    )

    cancel_requested = run_service.cancel_run(started.run_id, reason="transport_stop", state_path=state_path)
    assert cancel_requested is not None
    assert cancel_requested.status == run_service.STATUS_CANCEL_REQUESTED
    assert cancel_requested.cancel_requested is True
    assert run_service.is_cancel_requested(started.run_id, state_path=state_path) is True
    assert [row.run_id for row in run_service.list_active(state_path=state_path)] == [started.run_id]

    cancelled = run_service.update_run(
        started.run_id,
        status=run_service.STATUS_CANCELLED,
        cancel_requested=True,
        error="Cancelled by transport.",
        state_path=state_path,
    )
    assert cancelled is not None
    assert cancelled.status == run_service.STATUS_CANCELLED
    assert cancelled.error == "Cancelled by transport."
    assert run_service.list_active(state_path=state_path) == []


def test_append_followup_persists_to_run_state(tmp_path: Path) -> None:
    state_path = tmp_path / "run_service_state.json"
    started = run_service.start_run(
        task_id="aggregate_report",
        domain="gridtool",
        session_id=9401,
        state_path=state_path,
    )

    updated = run_service.append_followup(
        started.run_id,
        "retry with stricter parser",
        "operator",
        1730000000.5,
        state_path=state_path,
    )
    assert updated is not None
    assert updated.followups is not None
    assert updated.followups[-1]["text"] == "retry with stricter parser"
    assert updated.followups[-1]["source"] == "operator"
    assert updated.followups[-1]["ts"] == 1730000000.5

    persisted = run_service.get_run(started.run_id, state_path=state_path)
    assert persisted is not None
    assert persisted.followups is not None
    assert len(persisted.followups) == 1
    assert persisted.followups[0]["text"] == "retry with stricter parser"


@pytest.mark.parametrize(
    ("text", "source", "ts"),
    [
        ("", "operator", 1730000000.5),
        ("valid", "", 1730000000.5),
        ("valid", "operator", "not-a-number"),
    ],
)
def test_append_followup_rejects_invalid_payload(
    tmp_path: Path,
    text: str,
    source: str,
    ts: Any,
) -> None:
    state_path = tmp_path / "run_service_state.json"
    started = run_service.start_run(
        task_id="aggregate_report",
        domain="gridtool",
        session_id=9402,
        state_path=state_path,
    )
    with pytest.raises(run_service.RunServiceError):
        run_service.append_followup(
            started.run_id,
            text,
            source,
            ts,
            state_path=state_path,
        )


def test_stream_run_filters_lifecycle_events(tmp_path: Path) -> None:
    state_path = tmp_path / "run_service_state.json"
    lifecycle_path = tmp_path / "run_lifecycle.jsonl"
    started = run_service.start_run(
        task_id="aggregate_report",
        domain="gridtool",
        session_id=9501,
        state_path=state_path,
    )
    lifecycle_path.write_text(
        "\n".join(
            [
                json.dumps({"run_id": started.run_id, "ts": 10.0, "event": "queued"}),
                json.dumps({"run_id": "run_other", "ts": 11.0, "event": "step"}),
                json.dumps({"run_id": started.run_id, "ts": 12.0, "event": "step"}),
                json.dumps({"run_id": started.run_id, "ts": 13.0, "event": "completed"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    filtered = run_service.list_events(
        started.run_id,
        from_ts=10.0,
        max_events=10,
        lifecycle_path=lifecycle_path,
    )
    assert [row["ts"] for row in filtered] == [12.0, 13.0]

    streamed = run_service.stream_run(
        started.run_id,
        from_ts=12.0,
        max_events=1,
        state_path=state_path,
        lifecycle_path=lifecycle_path,
    )
    assert streamed["run"] is not None
    assert streamed["run"].run_id == started.run_id
    assert [row["ts"] for row in streamed["events"]] == [13.0]


def test_list_events_without_cursor_returns_latest_tail(tmp_path: Path) -> None:
    state_path = tmp_path / "run_service_state.json"
    lifecycle_path = tmp_path / "run_lifecycle.jsonl"
    started = run_service.start_run(
        task_id="aggregate_report",
        domain="gridtool",
        session_id=9601,
        state_path=state_path,
    )
    lifecycle_path.write_text(
        "\n".join(
            [
                json.dumps({"run_id": started.run_id, "ts": 1.0, "event": "queued"}),
                json.dumps({"run_id": started.run_id, "ts": 2.0, "event": "started"}),
                json.dumps({"run_id": started.run_id, "ts": 3.0, "event": "step"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    tail = run_service.list_events(
        started.run_id,
        max_events=2,
        lifecycle_path=lifecycle_path,
    )
    assert [row["ts"] for row in tail] == [2.0, 3.0]


def test_run_cli_agent_script_old_args_still_work(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state_path = tmp_path / "run_service_state.json"
    captured: dict[str, Any] = {}

    monkeypatch.setattr(run_cli_agent_script.run_service, "DEFAULT_STATE_PATH", state_path)
    monkeypatch.setattr(run_cli_agent_script, "load_config", lambda: object())
    monkeypatch.setattr(
        run_cli_agent_script,
        "run_cli_agent",
        lambda **kwargs: captured.update(kwargs) or SimpleNamespace(metrics={"eval_passed": True}),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_cli_agent.py",
            "--task-id",
            "aggregate_report",
            "--session",
            "9301",
            "--domain",
            "gridtool",
        ],
    )

    rc = run_cli_agent_script.main()
    assert rc == 0
    assert captured["task_id"] == "aggregate_report"
    assert captured["session_id"] == 9301
    assert captured["domain"] == "gridtool"
    assert callable(captured["on_step"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["run_id"].startswith("run_")
