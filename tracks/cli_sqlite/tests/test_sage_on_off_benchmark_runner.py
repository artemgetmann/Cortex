from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tracks.cli_sqlite.scripts import run_sage_on_off_benchmark


def _payload(
    *,
    transfer_pass_rate: float,
    overall_pass_rate: float,
    transfer_steps: float | None,
    repeated_delta: float | None,
    did_learning_improve: bool,
    activations: float = 0.0,
    retrieval_help_ratio: float = 0.0,
) -> dict[str, Any]:
    return {
        "did_learning_improve": did_learning_improve,
        "overall": {
            "pass_rate": overall_pass_rate,
            "median_steps_to_success": transfer_steps,
        },
        "transfer": {
            "pass_rate": transfer_pass_rate,
            "median_steps_to_success": transfer_steps,
            "median_repeated_error_delta": repeated_delta,
            "mean_lesson_activations": activations,
            "mean_retrieval_help_ratio": retrieval_help_ratio,
        },
    }


def test_build_compare_payload_marks_improved_when_transfer_pass_lifts() -> None:
    compare = run_sage_on_off_benchmark.build_compare_payload(
        self_edit_on_payload=_payload(
            transfer_pass_rate=0.8,
            overall_pass_rate=0.9,
            transfer_steps=4.0,
            repeated_delta=-0.8,
            did_learning_improve=True,
            activations=1.2,
            retrieval_help_ratio=0.4,
        ),
        self_edit_off_payload=_payload(
            transfer_pass_rate=0.4,
            overall_pass_rate=0.6,
            transfer_steps=6.0,
            repeated_delta=-0.2,
            did_learning_improve=False,
            activations=0.4,
            retrieval_help_ratio=0.1,
        ),
        config={"sessions": 5, "suites": ["sqlite"], "arms": ["docs_on__mode_lossy__lessons_on"]},
    )
    assert compare["verdict"] == "improved"
    assert compare["deltas"]["transfer_pass_rate_delta"] > 0.0
    assert compare["deltas"]["overall_pass_rate_delta"] > 0.0
    assert compare["deltas"]["transfer_median_steps_to_success_improvement"] > 0.0


def test_build_compare_payload_marks_no_improvement_when_transfer_regresses() -> None:
    compare = run_sage_on_off_benchmark.build_compare_payload(
        self_edit_on_payload=_payload(
            transfer_pass_rate=0.4,
            overall_pass_rate=0.5,
            transfer_steps=8.0,
            repeated_delta=0.2,
            did_learning_improve=False,
        ),
        self_edit_off_payload=_payload(
            transfer_pass_rate=0.6,
            overall_pass_rate=0.6,
            transfer_steps=5.0,
            repeated_delta=-0.4,
            did_learning_improve=True,
        ),
        config={"sessions": 5, "suites": ["sqlite"], "arms": ["docs_on__mode_lossy__lessons_on"]},
    )
    assert compare["verdict"] == "no_improvement"
    assert compare["deltas"]["transfer_pass_rate_delta"] < 0.0


def test_main_runs_off_on_and_writes_compare_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def _fake_subprocess_run(cmd: list[str], cwd: str, check: bool) -> subprocess.CompletedProcess[str]:
        calls.append(list(cmd))
        output_json = Path(cmd[cmd.index("--output-json") + 1])
        output_md = Path(cmd[cmd.index("--output-md") + 1])
        self_edit_on = "--self-edit-mode" in cmd
        payload = _payload(
            transfer_pass_rate=0.8 if self_edit_on else 0.4,
            overall_pass_rate=0.8 if self_edit_on else 0.5,
            transfer_steps=4.0 if self_edit_on else 6.0,
            repeated_delta=-0.7 if self_edit_on else -0.1,
            did_learning_improve=self_edit_on,
            activations=1.0 if self_edit_on else 0.2,
            retrieval_help_ratio=0.3 if self_edit_on else 0.1,
        )
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
        output_md.write_text("# stub", encoding="utf-8")
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr(run_sage_on_off_benchmark.subprocess, "run", _fake_subprocess_run)

    compare_json = tmp_path / "sage_compare.json"
    compare_md = tmp_path / "sage_compare.md"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_sage_on_off_benchmark.py",
            "--sessions",
            "5",
            "--start-session",
            "99001",
            "--max-steps",
            "6",
            "--self-edit-off-json",
            str(tmp_path / "off.json"),
            "--self-edit-off-md",
            str(tmp_path / "off.md"),
            "--self-edit-on-json",
            str(tmp_path / "on.json"),
            "--self-edit-on-md",
            str(tmp_path / "on.md"),
            "--output-json",
            str(compare_json),
            "--output-md",
            str(compare_md),
        ],
    )

    rc = run_sage_on_off_benchmark.main()
    assert rc == 0
    assert len(calls) == 2
    assert any("--no-self-edit-mode" in cmd for cmd in calls)
    assert any("--self-edit-mode" in cmd for cmd in calls)
    assert all("--benchmark-deterministic" in cmd for cmd in calls)
    assert all("--benchmark-promoted-only" in cmd for cmd in calls)
    assert all("--suite" in cmd and "sqlite" in cmd for cmd in calls)
    assert all("--arm" in cmd and "docs_on__mode_lossy__lessons_on" in cmd for cmd in calls)

    payload = json.loads(compare_json.read_text(encoding="utf-8"))
    assert payload["verdict"] == "improved"
    assert payload["deltas"]["transfer_pass_rate_delta"] > 0.0
    summary_md = compare_md.read_text(encoding="utf-8")
    assert "# SAGE Self-Edit ON/OFF Compare" in summary_md
    assert "## Verdict" in summary_md
