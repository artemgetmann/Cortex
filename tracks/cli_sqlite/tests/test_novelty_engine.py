from __future__ import annotations

import json
from pathlib import Path

from tracks.cli_sqlite.novelty_engine import build_snapshot, snapshot_to_dict


def _write_metrics(
    sessions_root: Path,
    session_id: int,
    *,
    task_id: str,
    domain: str,
    eval_passed: bool,
    eval_score: float,
    error_count: int,
    lesson_activations: int = 0,
    retrieval_help_ratio: float = 0.0,
    repeated_error_signatures: list[str] | None = None,
) -> None:
    session_dir = sessions_root / f"session-{session_id:03d}"
    session_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "task_id": task_id,
        "domain": domain,
        "eval_passed": eval_passed,
        "eval_score": eval_score,
        "error_count": error_count,
        "lesson_activations": lesson_activations,
        "retrieval_help_ratio": retrieval_help_ratio,
        "repeated_error_signatures": repeated_error_signatures or [],
    }
    (session_dir / "metrics.json").write_text(json.dumps(payload), encoding="utf-8")


def test_build_snapshot_marks_unseen_families_as_new() -> None:
    snapshot = build_snapshot(sessions_root=Path("/tmp/does-not-exist-for-test"))

    assert snapshot.families
    assert any(item.bucket == "new_family" for item in snapshot.families)
    assert any(item.bucket == "new_family" for item in snapshot.recommendations)


def test_snapshot_retries_known_weak_family_and_probes_transfer(tmp_path: Path) -> None:
    sessions_root = tmp_path / "sessions"

    # Shell hotfix hard remains weak: low pass rate, errors high, same signature repeating.
    _write_metrics(
        sessions_root,
        1,
        task_id="shell_git_transfer_hotfix_hard",
        domain="shell",
        eval_passed=False,
        eval_score=0.2,
        error_count=8,
        lesson_activations=1,
        retrieval_help_ratio=0.5,
        repeated_error_signatures=["missing_hotfix_file"],
    )
    _write_metrics(
        sessions_root,
        2,
        task_id="shell_git_transfer_hotfix_hard",
        domain="shell",
        eval_passed=False,
        eval_score=0.25,
        error_count=7,
        lesson_activations=2,
        retrieval_help_ratio=1.0,
        repeated_error_signatures=["missing_hotfix_file"],
    )

    # SQLite base task is now learned, so the unseen audit sibling should become the transfer probe.
    for idx in range(3, 6):
        _write_metrics(
            sessions_root,
            idx,
            task_id="incremental_reconcile",
            domain="sqlite",
            eval_passed=True,
            eval_score=1.0,
            error_count=1,
            lesson_activations=2,
            retrieval_help_ratio=1.0,
        )

    snapshot = build_snapshot(sessions_root=sessions_root)
    payload = snapshot_to_dict(snapshot)

    weak = next(item for item in payload["recommendations"] if item["slot"] == "known_weak")
    transfer = next(item for item in payload["recommendations"] if item["slot"] == "transfer_probe")

    assert weak["task_id"] == "shell_git_transfer_hotfix_hard"
    assert weak["bucket"] == "known_weak"
    assert transfer["task_id"] == "incremental_reconcile_audit_transfer"
    assert transfer["bucket"] == "transfer_probe"


def test_saturated_family_is_deprioritized(tmp_path: Path) -> None:
    sessions_root = tmp_path / "sessions"
    for idx in range(1, 5):
        _write_metrics(
            sessions_root,
            idx,
            task_id="artic_search_basic",
            domain="artic",
            eval_passed=True,
            eval_score=1.0,
            error_count=0,
            lesson_activations=0,
            retrieval_help_ratio=0.0,
        )

    snapshot = build_snapshot(sessions_root=sessions_root)
    family = next(item for item in snapshot.families if item.family_id == "artic_search")

    assert family.bucket == "saturated"
    assert all(item.family_id != "artic_search" for item in snapshot.recommendations)
