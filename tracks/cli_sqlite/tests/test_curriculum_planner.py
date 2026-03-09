from __future__ import annotations

from pathlib import Path

import pytest

from tracks.cli_sqlite import curriculum_planner


def test_fixed_planner_keeps_seed_task() -> None:
    planner = curriculum_planner.FixedCurriculumPlanner(task_id="aggregate_report", domain="gridtool")
    first = planner.propose_next(run_index=1)
    second = planner.propose_next(run_index=2)

    assert first.task_id == "aggregate_report"
    assert second.task_id == "aggregate_report"
    assert first.domain == "gridtool"
    assert "fixed schedule" in first.rationale


def test_auto_planner_retries_unresolved_then_progresses() -> None:
    planner = curriculum_planner.AdaptiveCurriculumPlanner(
        seed_task_id="import_aggregate",
        domain="sqlite",
        candidates=curriculum_planner.build_curriculum_tasks(domain="sqlite", seed_task_id="import_aggregate"),
    )

    run_1 = planner.propose_next(run_index=1)
    assert run_1.task_id == "import_aggregate"

    planner.record_outcome(
        curriculum_planner.CurriculumOutcome(
            run_index=1,
            task_id=run_1.task_id,
            domain=run_1.domain,
            score=0.2,
            passed=False,
            steps=8,
            tool_errors=1,
            repeated_error_signatures=("schema",),
        )
    )
    run_2 = planner.propose_next(run_index=2)
    assert run_2.task_id == "import_aggregate"

    planner.record_outcome(
        curriculum_planner.CurriculumOutcome(
            run_index=2,
            task_id=run_2.task_id,
            domain=run_2.domain,
            score=1.0,
            passed=True,
            steps=4,
            tool_errors=0,
            repeated_error_signatures=(),
        )
    )
    planner.record_outcome(
        curriculum_planner.CurriculumOutcome(
            run_index=3,
            task_id=run_2.task_id,
            domain=run_2.domain,
            score=1.0,
            passed=True,
            steps=4,
            tool_errors=0,
            repeated_error_signatures=(),
        )
    )

    run_4 = planner.propose_next(run_index=4)
    assert run_4.task_id != "import_aggregate"


def test_novelty_planner_prefers_domain_recommendations(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _Snapshot:
        recommendations = [
            type(
                "Rec",
                (),
                {
                    "domain": "shell",
                    "task_id": "shell_git_transfer_hotfix_hard",
                    "slot": "known_weak",
                    "bucket": "known_weak",
                    "novelty_score": 2.5,
                },
            )()
        ]
        families = []

    monkeypatch.setattr("tracks.cli_sqlite.novelty_engine.build_snapshot", lambda sessions_root: _Snapshot())
    planner = curriculum_planner.NoveltyCurriculumPlanner(
        seed_task_id="shell_git_transfer_hotfix",
        domain="shell",
        sessions_root=tmp_path / "sessions",
    )

    decision = planner.propose_next(run_index=1)

    assert decision.task_id == "shell_git_transfer_hotfix_hard"
    assert decision.domain == "shell"
    assert "novelty slot=known_weak" in decision.rationale
