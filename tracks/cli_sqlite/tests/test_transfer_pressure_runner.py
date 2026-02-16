from __future__ import annotations

import json
import sys
from typing import Any

import pytest

from tracks.cli_sqlite.scripts import run_transfer_pressure


def test_transfer_pressure_runner_emits_payload_and_arm_config(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state: dict[str, int] = {"clear_lessons": 0, "clear_escalation": 0}
    calls: list[dict[str, Any]] = []

    monkeypatch.setattr(run_transfer_pressure, "load_config", lambda: object())
    monkeypatch.setattr(
        run_transfer_pressure,
        "_clear_lessons_store",
        lambda: state.__setitem__("clear_lessons", state["clear_lessons"] + 1),
    )
    monkeypatch.setattr(
        run_transfer_pressure,
        "_clear_escalation",
        lambda: state.__setitem__("clear_escalation", state["clear_escalation"] + 1),
    )
    monkeypatch.setattr(run_transfer_pressure, "_snapshot_learning_state", lambda: {"ok": "1"})
    monkeypatch.setattr(run_transfer_pressure, "_restore_learning_state", lambda snapshot: None)

    def _fake_run_phase(**kwargs: Any) -> list[dict[str, Any]]:
        calls.append(dict(kwargs))
        arm = str(kwargs["arm"])
        sessions = int(kwargs["sessions"])
        start_session = int(kwargs["start_session"])
        transfer_max = int(kwargs["transfer_retrieval_max_results"])
        rows: list[dict[str, Any]] = []
        for idx in range(sessions):
            rows.append(
                {
                    "arm": arm,
                    "domain": kwargs["domain"],
                    "task_id": kwargs["task_id"],
                    "run": idx + 1,
                    "session_id": start_session + idx,
                    "passed": arm != "strict_only",
                    "score": 1.0 if arm != "strict_only" else 0.0,
                    "steps": 4,
                    "tool_errors": 0 if arm != "strict_only" else 2,
                    "lesson_activations": 2 if transfer_max > 0 else 0,
                    "strict_lane_activations": 1 if transfer_max > 0 else 0,
                    "transfer_lane_activations": 1 if transfer_max > 0 else 0,
                    "retrieval_help_ratio": 1.0 if transfer_max > 0 else 0.0,
                    "fingerprint_recurrence_before": 0.0,
                    "fingerprint_recurrence_after": 0.0,
                    "promoted_count": 0,
                    "suppressed_count": 0,
                    "validation_retry_attempts": 0,
                    "validation_retry_capped_events": 0,
                    "transfer_policy": "auto",
                    "transfer_enabled": transfer_max > 0,
                    "transfer_only_activation": False,
                    "mixed_activation": transfer_max > 0,
                    "recurrence_increase": False,
                    "elapsed_s": 0.1,
                }
            )
        return rows

    monkeypatch.setattr(run_transfer_pressure, "_run_phase", _fake_run_phase)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_transfer_pressure.py",
            "--seed-sessions",
            "1",
            "--pressure-sessions",
            "2",
            "--start-session",
            "65000",
            "--learning-mode",
            "strict",
            "--auto-transfer-max-results",
            "1",
            "--auto-transfer-score-weight",
            "0.35",
        ],
    )

    rc = run_transfer_pressure.main()
    assert rc == 0
    assert state["clear_lessons"] == 1
    assert state["clear_escalation"] >= 1

    # Calls: seed, strict_only, auto_transfer
    assert [str(c["arm"]) for c in calls] == ["seed", "strict_only", "auto_transfer"]
    assert int(calls[1]["transfer_retrieval_max_results"]) == 0
    assert int(calls[2]["transfer_retrieval_max_results"]) == 1

    out = capsys.readouterr().out
    marker = "JSON summary:\n"
    assert marker in out
    payload = json.loads(out.split(marker, 1)[1].strip())
    assert set(payload.keys()) == {"config", "seed", "arms", "deltas", "caveats"}
    assert "strict_only" in payload["arms"]
    assert "auto_transfer" in payload["arms"]
    assert payload["arms"]["auto_transfer"]["summary"]["transfer_lane_activations_total"] > 0
