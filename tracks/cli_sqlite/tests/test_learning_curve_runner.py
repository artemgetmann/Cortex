from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from tracks.cli_sqlite.scripts import run_learning_curve


def test_learning_curve_default_curriculum_is_fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    monkeypatch.setattr(run_learning_curve, "load_config", lambda: object())

    def _fake_run_cli_agent(**kwargs: Any) -> SimpleNamespace:
        calls.append(dict(kwargs))
        return SimpleNamespace(
            metrics={
                "eval_score": 1.0,
                "eval_passed": True,
                "steps": 3,
                "tool_errors": 0,
                "lessons_loaded": 0,
                "lessons_generated": 0,
                "repeated_error_signatures": [],
            }
        )

    monkeypatch.setattr(run_learning_curve, "run_cli_agent", _fake_run_cli_agent)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_learning_curve.py",
            "--task-id",
            "aggregate_report",
            "--domain",
            "gridtool",
            "--sessions",
            "3",
            "--start-session",
            "72000",
            "--max-steps",
            "4",
            "--learning-mode",
            "strict",
        ],
    )

    rc = run_learning_curve.main()
    assert rc == 0
    assert len(calls) == 3
    assert [str(call["task_id"]) for call in calls] == ["aggregate_report", "aggregate_report", "aggregate_report"]
    assert [str(call["domain"]) for call in calls] == ["gridtool", "gridtool", "gridtool"]
    assert all(bool(call.get("benchmark_deterministic", False)) is False for call in calls)
    assert all(bool(call.get("benchmark_promoted_only", False)) is False for call in calls)
    assert all(bool(call.get("benchmark_placebo", False)) is False for call in calls)


def test_learning_curve_auto_mode_uses_curriculum_planner(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    recorded_runs: list[int] = []
    recorded_outcomes: list[Any] = []

    monkeypatch.setattr(run_learning_curve, "load_config", lambda: object())

    class _FakePlanner:
        def propose_next(self, *, run_index: int):
            recorded_runs.append(int(run_index))
            if run_index == 1:
                return SimpleNamespace(
                    task_id="shell_excel_build_report",
                    domain="shell",
                    rationale="auto score=1.0",
                )
            return SimpleNamespace(
                task_id="shell_excel_multi_summary",
                domain="shell",
                rationale="auto score=1.1",
            )

        def record_outcome(self, outcome: Any) -> None:
            recorded_outcomes.append(outcome)

    monkeypatch.setattr(
        run_learning_curve,
        "create_curriculum_planner",
        lambda mode, task_id, domain: _FakePlanner(),
    )

    def _fake_run_cli_agent(**kwargs: Any) -> SimpleNamespace:
        calls.append(dict(kwargs))
        idx = len(calls)
        return SimpleNamespace(
            metrics={
                "eval_score": 0.0 if idx == 1 else 1.0,
                "eval_passed": idx != 1,
                "steps": 4,
                "tool_errors": 1 if idx == 1 else 0,
                "lessons_loaded": 0,
                "lessons_generated": 1,
                "repeated_error_signatures": ["files"] if idx == 1 else [],
            }
        )

    monkeypatch.setattr(run_learning_curve, "run_cli_agent", _fake_run_cli_agent)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_learning_curve.py",
            "--task-id",
            "shell_excel_build_report",
            "--domain",
            "shell",
            "--curriculum-mode",
            "auto",
            "--sessions",
            "2",
            "--start-session",
            "72100",
            "--max-steps",
            "4",
            "--learning-mode",
            "strict",
        ],
    )

    rc = run_learning_curve.main()
    assert rc == 0
    assert [str(call["task_id"]) for call in calls] == [
        "shell_excel_build_report",
        "shell_excel_multi_summary",
    ]
    assert all(bool(call.get("benchmark_deterministic", False)) is False for call in calls)
    assert all(bool(call.get("benchmark_promoted_only", False)) is False for call in calls)
    assert all(bool(call.get("benchmark_placebo", False)) is False for call in calls)
    assert recorded_runs == [1, 2]
    assert len(recorded_outcomes) == 2


def test_learning_curve_openai_defaults_executor_and_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    monkeypatch.setattr(run_learning_curve, "load_config", lambda: object())

    def _fake_run_cli_agent(**kwargs: Any) -> SimpleNamespace:
        calls.append(dict(kwargs))
        return SimpleNamespace(
            metrics={
                "eval_score": 1.0,
                "eval_passed": True,
                "steps": 1,
                "tool_errors": 0,
                "lessons_loaded": 0,
                "lessons_generated": 0,
                "repeated_error_signatures": [],
            }
        )

    monkeypatch.setattr(run_learning_curve, "run_cli_agent", _fake_run_cli_agent)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_learning_curve.py",
            "--task-id",
            "aggregate_report",
            "--domain",
            "gridtool",
            "--sessions",
            "1",
            "--start-session",
            "72200",
            "--llm-backend",
            "openai",
        ],
    )

    rc = run_learning_curve.main()
    assert rc == 0
    assert len(calls) == 1
    assert calls[0]["llm_backend"] == "openai"
    assert calls[0]["model_executor"] == "gpt-5-nano"
    assert calls[0]["model_critic"] == "gpt-5-nano"
    assert calls[0]["model_judge"] == "gpt-5-nano"
