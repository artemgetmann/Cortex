from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from tracks.cli_sqlite.scripts import run_mixed_benchmark


def test_mixed_benchmark_runner_emits_expected_protocol_and_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path,
) -> None:
    cleared: dict[str, bool] = {"lessons": False, "escalation": False}
    run_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(run_mixed_benchmark, "SESSIONS_ROOT", tmp_path / "sessions")

    monkeypatch.setattr(run_mixed_benchmark, "load_config", lambda: object())
    monkeypatch.setattr(run_mixed_benchmark, "_clear_escalation", lambda: cleared.__setitem__("escalation", True))
    monkeypatch.setattr(run_mixed_benchmark, "_clear_lessons", lambda: cleared.__setitem__("lessons", True))

    def _fake_run_cli_agent(**kwargs: Any) -> SimpleNamespace:
        run_calls.append(dict(kwargs))
        session_id = int(kwargs.get("session_id", 0))
        return SimpleNamespace(
            metrics={
                "eval_passed": True,
                "eval_score": 1.0,
                "steps": 4,
                "tool_errors": 0,
                "lessons_loaded": session_id % 2,
                "lessons_generated": 1,
                "lesson_activations": 0,
                "usage": [{"input_tokens": 150, "output_tokens": 40}],
            }
        )

    monkeypatch.setattr(run_mixed_benchmark, "run_cli_agent", _fake_run_cli_agent)
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

    assert "[variant-scoreboard]" in out
    assert set(payload.keys()) == {
        "config",
        "protocol",
        "phase_summary",
        "overall_summary",
        "retention_delta",
        "runs",
        "variant_scoreboard",
    }
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
    assert all("variant_id" in row for row in payload["runs"])
    assert all("variant_score" in row for row in payload["runs"])
    scoreboard = payload["variant_scoreboard"]
    assert scoreboard["rows_written"] == 5
    assert len(scoreboard["rows"]) == 5
    assert isinstance(scoreboard["best_by_task"], dict)
    assert run_calls
