from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tracks.cli_sqlite import agent_cli
from tracks.cli_sqlite.scripts import run_fl_studio_demo


def _make_screenshots(sessions_root: Path, session_id: int, count: int) -> None:
    session_dir = sessions_root / f"session-{session_id:03d}"
    session_dir.mkdir(parents=True, exist_ok=True)
    for idx in range(count):
        path = session_dir / f"shot-{idx}.png"
        path.write_bytes(b"fake-png-%d" % idx)


def test_run_fl_studio_demo_orders_phases_and_saves_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sessions_root = tmp_path / "sessions"
    monkeypatch.setattr(agent_cli, "SESSIONS_ROOT", sessions_root)
    monkeypatch.setattr(run_fl_studio_demo, "load_config", lambda: SimpleNamespace())

    calls: list[dict[str, object]] = []

    def fake_run_cli_agent(**kwargs: object) -> SimpleNamespace:
        calls.append({k: v for k, v in kwargs.items()})
        metrics = {
            "eval_score": float(len(calls)),
            "eval_passed": len(calls) % 2 == 0,
        }
        return SimpleNamespace(metrics=metrics)

    monkeypatch.setattr(run_fl_studio_demo, "run_cli_agent", fake_run_cli_agent)

    start_session = 5
    for sid in range(start_session, start_session + len(run_fl_studio_demo.PHASES)):
        _make_screenshots(sessions_root, sid, 2)

    summary_path = tmp_path / "demo_summary.json"
    argv = [
        "run_fl_studio_demo.py",
        "--session",
        str(start_session),
        "--max-screenshots",
        "1",
        "--output-json",
        str(summary_path),
    ]
    monkeypatch.setattr(sys, "argv", argv)

    result = run_fl_studio_demo.main()
    assert result == 0
    assert len(calls) == len(run_fl_studio_demo.PHASES)
    assert [call["session_id"] for call in calls] == [start_session + idx for idx in range(len(run_fl_studio_demo.PHASES))]

    data = json.loads(summary_path.read_text(encoding="utf-8"))
    assert data["config"]["task_id"] == "fl_studio_demo"
    assert len(data["phases"]) == len(run_fl_studio_demo.PHASES)
    for idx, phase in enumerate(run_fl_studio_demo.PHASES):
        row = data["phases"][idx]
        assert row["phase"] == phase.name
        assert row["judge_reference"] == phase.judge_reference
        assert row["screenshots"]
        assert row["score"] == float(idx + 1)

    summary = data["summary"]
    assert summary["phase_count"] == len(run_fl_studio_demo.PHASES)
    assert summary["sessions"] == [start_session + idx for idx in range(len(run_fl_studio_demo.PHASES))]
    assert summary["total_screenshots"] == len(run_fl_studio_demo.PHASES)
    expected_pass_rate = 1 / len(run_fl_studio_demo.PHASES)
    assert abs(summary["pass_rate"] - expected_pass_rate) < 1e-9
