from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from tracks.cli_sqlite.scripts import run_realworld_learning_benchmark


def test_realworld_learning_benchmark_emits_expected_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    clear_calls: dict[str, int] = {"count": 0}
    run_calls: list[dict[str, Any]] = []

    monkeypatch.setattr(run_realworld_learning_benchmark, "load_config", lambda: object())
    monkeypatch.setattr(
        run_realworld_learning_benchmark,
        "_clear_learning_state",
        lambda: clear_calls.__setitem__("count", clear_calls["count"] + 1),
    )

    def _fake_run_cli_agent(**kwargs: Any) -> SimpleNamespace:
        run_calls.append(dict(kwargs))
        task_id = str(kwargs.get("task_id", ""))
        run_index = len(run_calls)
        # Deterministic synthetic behavior:
        # - transfer passes when lessons are enabled; otherwise fails every other run.
        lessons_on = bool(kwargs.get("posttask_learn", False))
        is_transfer = "transfer" in task_id
        passed = (not is_transfer) or lessons_on or (run_index % 2 == 0)
        before = 2.0
        after = 1.0 if passed else 3.0
        return SimpleNamespace(
            metrics={
                "eval_passed": passed,
                "eval_score": 1.0 if passed else 0.0,
                "steps": 4 if passed else 8,
                "tool_errors": 0 if passed else 2,
                "lessons_loaded": 1 if lessons_on else 0,
                "lessons_generated": 1 if lessons_on else 0,
                "repeated_error_signatures": ["fp_a"] if not passed else [],
                "v2_fingerprint_recurrence_before": before,
                "v2_fingerprint_recurrence_after": after,
            }
        )

    monkeypatch.setattr(run_realworld_learning_benchmark, "run_cli_agent", _fake_run_cli_agent)

    output_json = tmp_path / "realworld.json"
    output_md = tmp_path / "realworld.md"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_realworld_learning_benchmark.py",
            "--sessions",
            "4",
            "--start-session",
            "88000",
            "--max-steps",
            "6",
            "--learning-mode",
            "strict",
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ],
    )

    rc = run_realworld_learning_benchmark.main()
    assert rc == 0
    assert clear_calls["count"] >= 8
    assert run_calls
    assert all(bool(call.get("benchmark_deterministic", False)) is False for call in run_calls)
    assert all(bool(call.get("benchmark_promoted_only", False)) is False for call in run_calls)

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert set(payload.keys()) == {
        "config",
        "task_schedule",
        "overall",
        "transfer",
        "arms",
        "runs",
        "did_learning_improve",
    }
    assert len(payload["arms"]) == 8
    assert len(payload["runs"]) == 32
    assert bool(payload["config"]["benchmark_deterministic"]) is False
    assert bool(payload["config"]["benchmark_promoted_only"]) is False
    docs_off_rows = [row for row in payload["runs"] if not bool(row.get("docs_enabled", True))]
    assert docs_off_rows
    assert all(str(row.get("doc_mode")) == "none" for row in docs_off_rows)
    first_row = payload["runs"][0]
    assert "lesson_activations" in first_row
    assert "lesson_activations_by_step" in first_row
    assert "promoted_count" in first_row
    assert "suppressed_count" in first_row
    assert "retrieval_help_ratio" in first_row
    assert "transfer_lane_activations" in first_row
    assert "fingerprint_recurrence_before" in first_row
    assert "fingerprint_recurrence_after" in first_row
    assert set(payload["overall"]["success_rate_by_session"].keys()) == {"1", "2", "3", "4"}
    assert payload["transfer"]["run_count"] > 0
    assert "mean_lesson_activations_by_step" in payload["overall"]
    assert "activation_nonzero_run_count" in payload["overall"]

    schedule_task_ids = [str(item["task_id"]) for item in payload["task_schedule"]]
    assert "shell_git_train_release_flow" in schedule_task_ids
    assert "shell_git_transfer_hotfix" in schedule_task_ids
    assert "import_aggregate" in schedule_task_ids
    assert "incremental_reconcile" in schedule_task_ids
    assert "shell_excel_build_report" in schedule_task_ids
    assert "shell_excel_multi_summary" in schedule_task_ids

    summary_md = output_md.read_text(encoding="utf-8")
    assert "## Metric Glossary" in summary_md
    assert "## How To Read This Report" in summary_md
    assert "## Artifact Notes" in summary_md
    assert "| arm_id | docs | doc_mode | lessons | pass_rate |" in summary_md
    assert "mean_lesson_activations_by_step" in summary_md


def test_learning_gate_requires_activation_and_retrieval_lift() -> None:
    rows = [
        {"run_index": 1, "phase": "transfer", "passed": False, "lesson_activations": 0, "retrieval_help_ratio": 0.0},
        {"run_index": 2, "phase": "transfer", "passed": True, "lesson_activations": 0, "retrieval_help_ratio": 0.0},
    ]
    gate = run_realworld_learning_benchmark._learning_gate(rows)
    assert gate["transfer_pass_lift"] is True
    assert gate["activation_nonzero"] is False
    assert gate["retrieval_help_ratio_lift"] is False
    assert gate["did_learning_improve"] is False
    assert gate["transfer_pass_delta"] > 0.0


def test_learning_gate_reports_numeric_deltas() -> None:
    rows = [
        {"run_index": 1, "phase": "transfer", "passed": False, "lesson_activations": 1, "retrieval_help_ratio": 0.1},
        {"run_index": 2, "phase": "transfer", "passed": True, "lesson_activations": 2, "retrieval_help_ratio": 0.4},
    ]
    gate = run_realworld_learning_benchmark._learning_gate(rows)
    assert gate["activation_delta"] > 0.0
    assert gate["retrieval_help_ratio_delta"] > 0.0
