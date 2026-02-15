from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from tracks.cli_sqlite import agent_cli
from tracks.cli_sqlite.scripts import run_architecture_ab


def test_ab_helpers_compute_expected_metrics() -> None:
    metrics = {
        "usage": [
            {"input_tokens": 100, "output_tokens": 25},
            {"input_tokens": 200, "output_tokens": 50},
            {"input_tokens": "bad", "output_tokens": None},
        ]
    }
    assert run_architecture_ab._token_estimate(metrics) == 375

    rows = [
        {"passed": False, "score": 0.0, "steps": 8, "tool_errors": 7, "tokens_est": 1000, "elapsed_s": 10.0},
        {"passed": True, "score": 1.0, "steps": 4, "tool_errors": 1, "tokens_est": 600, "elapsed_s": 8.0},
    ]
    agg = run_architecture_ab._aggregate(rows)
    assert agg == {
        "pass_rate": 0.5,
        "mean_score": 0.5,
        "mean_steps": 6.0,
        "mean_tool_errors": 4.0,
        "total_tokens_est": 1600,
        "total_elapsed_s": 18.0,
    }


def test_ab_main_emits_payload_with_both_arms_and_deltas(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(run_architecture_ab, "load_config", lambda: object())
    monkeypatch.setattr(run_architecture_ab, "_clear_lessons_and_escalation", lambda: None)

    def _fake_run_agent_for_arm(*, architecture_mode: str, kwargs: dict, architecture_mode_supported: dict, caveats: list[str]):
        architecture_mode_supported["value"] = True
        run_idx = int(kwargs["session_id"]) % 10
        if architecture_mode == "full":
            score = 0.0 if run_idx == 1 else 1.0
            passed = score >= 0.75
            usage = [{"input_tokens": 800, "output_tokens": 120}]
        else:
            score = 1.0
            passed = True
            usage = [{"input_tokens": 500, "output_tokens": 70}]
        return SimpleNamespace(
            metrics={
                "eval_score": score,
                "eval_passed": passed,
                "steps": 6 if architecture_mode == "full" else 4,
                "tool_errors": 3 if architecture_mode == "full" else 1,
                "lessons_loaded": max(0, run_idx - 1),
                "lessons_generated": 2,
                "elapsed_s": 0.01,
                "usage": usage,
            }
        )

    monkeypatch.setattr(run_architecture_ab, "_run_agent_for_arm", _fake_run_agent_for_arm)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_architecture_ab.py",
            "--domain",
            "fluxtool",
            "--task-id",
            "aggregate_report_holdout",
            "--learning-mode",
            "strict",
            "--sessions",
            "2",
            "--start-session",
            "61000",
            "--max-steps",
            "8",
            "--bootstrap",
            "--mixed-errors",
            "--clear-lessons-between-arms",
        ],
    )

    rc = run_architecture_ab.main()
    assert rc == 0

    out = capsys.readouterr().out
    payload = json.loads(out.split("JSON summary:\n", 1)[1].strip())
    assert set(payload["arms"].keys()) == {"full", "simplified"}
    assert {"pass_rate", "mean_score", "mean_steps", "mean_tool_errors", "total_tokens_est", "total_elapsed_s"} <= set(
        payload["deltas"].keys()
    )
    assert payload["arms"]["simplified"]["pass_rate"] >= payload["arms"]["full"]["pass_rate"]
    assert len(payload["runs"]["full"]) == 2
    assert len(payload["runs"]["simplified"]) == 2


def test_architecture_mode_normalization_rejects_invalid() -> None:
    assert agent_cli._normalize_architecture_mode("  FULL  ") == "full"
    assert agent_cli._normalize_architecture_mode("simplified") == "simplified"
    with pytest.raises(ValueError):
        agent_cli._normalize_architecture_mode("__invalid_architecture_mode__")
