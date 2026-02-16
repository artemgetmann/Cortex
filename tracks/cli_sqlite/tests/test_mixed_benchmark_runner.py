from __future__ import annotations

import json
import sys
from typing import Any

import pytest

from tracks.cli_sqlite.scripts import run_mixed_benchmark


def test_mixed_benchmark_runner_emits_expected_protocol_and_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cleared: dict[str, bool] = {"lessons": False, "escalation": False}

    monkeypatch.setattr(run_mixed_benchmark, "load_config", lambda: object())
    monkeypatch.setattr(run_mixed_benchmark, "_clear_escalation", lambda: cleared.__setitem__("escalation", True))
    monkeypatch.setattr(run_mixed_benchmark, "_clear_lessons", lambda: cleared.__setitem__("lessons", True))

    def _fake_run_phase(**kwargs: Any) -> list[dict[str, Any]]:
        phase = str(kwargs["phase"])
        domain = str(kwargs["domain"])
        task_id = str(kwargs["task_id"])
        n_runs = int(kwargs["n_runs"])
        start_session = int(kwargs["start_session"])
        rows: list[dict[str, Any]] = []
        for idx in range(n_runs):
            rows.append(
                {
                    "phase": phase,
                    "domain": domain,
                    "task_id": task_id,
                    "run": idx + 1,
                    "session_id": start_session + idx,
                    "passed": True,
                    "score": 1.0,
                    "steps": 4,
                    "tool_errors": 0,
                    "lessons_loaded": idx,
                    "lessons_generated": 1,
                    "lesson_activations": 0,
                    "elapsed_s": 0.2,
                }
            )
        return rows

    monkeypatch.setattr(run_mixed_benchmark, "_run_phase", _fake_run_phase)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_mixed_benchmark.py",
            "--grid-runs",
            "1",
            "--fluxtool-runs",
            "1",
            "--shell-runs",
            "1",
            "--sqlite-runs",
            "1",
            "--retention-runs",
            "1",
            "--start-session",
            "64000",
            "--max-steps",
            "6",
            "--learning-mode",
            "strict",
            "--clear-lessons",
        ],
    )

    rc = run_mixed_benchmark.main()
    assert rc == 0
    assert cleared["escalation"] is True
    assert cleared["lessons"] is True

    out = capsys.readouterr().out
    marker = "JSON summary:\n"
    assert marker in out
    payload = json.loads(out.split(marker, 1)[1].strip())

    assert set(payload.keys()) == {"config", "protocol", "phase_summary", "overall_summary", "retention_delta", "runs"}
    protocol = payload["protocol"]
    assert [item["phase"] for item in protocol] == [
        "grid_warmup",
        "fluxtool_interference",
        "shell_excel_interference",
        "sqlite_interference",
        "grid_retention",
    ]
    assert [item["domain"] for item in protocol] == ["gridtool", "fluxtool", "shell", "sqlite", "gridtool"]
    assert len(payload["runs"]) == 5
    assert [row["session_id"] for row in payload["runs"]] == [64000, 64001, 64002, 64003, 64004]
