from __future__ import annotations

from tracks.cli_sqlite.variant_scoreboard import (
    append_variant_score_entry,
    read_variant_score_rows,
    select_best_variant,
)


def test_append_and_read_variant_scoreboard_rows(tmp_path) -> None:
    sessions_root = tmp_path / "sessions"
    metrics = {
        "eval_passed": True,
        "eval_score": 0.9,
        "steps": 4,
        "tool_errors": 1,
        "lessons_loaded": 2,
        "lessons_generated": 1,
        "usage": [{"input_tokens": 120, "output_tokens": 30, "cache_read_input_tokens": 20}],
    }
    row = append_variant_score_entry(
        sessions_root=sessions_root,
        run_source="unit_test",
        session_id=901,
        task_id="shell_git_transfer_hotfix_hard",
        domain="shell",
        variant_id="alpha",
        variant_source="runtime_spec",
        elapsed_s=3.5,
        metrics=metrics,
        run_index=1,
        phase="phase_a",
        variant_family="shell_git_transfer_hotfix_hard",
    )
    assert row["variant_id"] == "alpha"
    assert row["total_with_cache_tokens"] == 170
    assert float(row["variant_score"]) > 0.0

    rows = read_variant_score_rows(sessions_root=sessions_root)
    assert len(rows) == 1
    stored = rows[0]
    assert stored["run_source"] == "unit_test"
    assert stored["raw_metrics"]["steps"] == 4
    assert stored["raw_metrics"]["total_with_cache_tokens"] == 170


def test_select_best_variant_prefers_higher_score() -> None:
    rows = [
        {
            "variant_family": "shell_git_transfer_hotfix_hard",
            "variant_id": "alpha",
            "variant_score": 0.62,
            "quality_score": 0.60,
            "speed_score": 0.55,
            "cost_score": 0.50,
            "elapsed_s": 8.0,
            "steps": 8,
            "total_with_cache_tokens": 1200,
            "tool_errors": 2,
            "passed": True,
            "session_id": 10,
        },
        {
            "variant_family": "shell_git_transfer_hotfix_hard",
            "variant_id": "beta",
            "variant_score": 0.71,
            "quality_score": 0.67,
            "speed_score": 0.62,
            "cost_score": 0.58,
            "elapsed_s": 6.0,
            "steps": 6,
            "total_with_cache_tokens": 900,
            "tool_errors": 1,
            "passed": True,
            "session_id": 11,
        },
    ]
    best = select_best_variant(rows, variant_family="shell_git_transfer_hotfix_hard")
    assert best is not None
    assert best["variant_id"] == "beta"


def test_select_best_variant_tie_breaks_deterministically() -> None:
    rows = [
        {
            "variant_family": "shell_git_transfer_hotfix_hard",
            "variant_id": "beta",
            "variant_score": 0.7,
            "quality_score": 0.6,
            "speed_score": 0.5,
            "cost_score": 0.4,
            "elapsed_s": 5.0,
            "steps": 5,
            "total_with_cache_tokens": 1000,
            "tool_errors": 1,
            "passed": True,
            "session_id": 21,
        },
        {
            "variant_family": "shell_git_transfer_hotfix_hard",
            "variant_id": "alpha",
            "variant_score": 0.7,
            "quality_score": 0.6,
            "speed_score": 0.5,
            "cost_score": 0.4,
            "elapsed_s": 5.0,
            "steps": 5,
            "total_with_cache_tokens": 1000,
            "tool_errors": 1,
            "passed": True,
            "session_id": 20,
        },
    ]
    best = select_best_variant(rows, variant_family="shell_git_transfer_hotfix_hard")
    assert best is not None
    assert best["variant_id"] == "alpha"
