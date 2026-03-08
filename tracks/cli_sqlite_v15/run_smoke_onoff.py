#!/usr/bin/env python3
"""Minimal v1.5 ON/OFF smoke wrapper for CLI Memory benchmarks.

The wrapper keeps the runtime policy locked and only exposes a small run
surface needed for repeated ON/OFF checks.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config import load_config
from tracks.cli_sqlite import agent_cli
from tracks.cli_sqlite_v15.profile import V15_LOCKED


# Locked v1.5 runtime policy.
LOCKED_BACKEND = V15_LOCKED.llm_backend
LOCKED_MODEL_EXECUTOR = V15_LOCKED.model_executor
LOCKED_MODEL_JUDGE = V15_LOCKED.model_judge
LOCKED_MODEL_CRITIC = V15_LOCKED.model_critic
LOCKED_SELF_EDIT_MODE = V15_LOCKED.self_edit_mode
LOCKED_BENCHMARK_DETERMINISTIC = V15_LOCKED.benchmark_deterministic
LOCKED_STRUCTURED_LESSONS_REQUIRED = V15_LOCKED.structured_lessons_required
LOCKED_CONTRACT_GAP_RETRY = V15_LOCKED.contract_gap_retry
LOCKED_CONTRACT_GAP_RETRY_STEPS = V15_LOCKED.contract_gap_retry_steps
LOCKED_CONTRACT_GAP_DETERMINISTIC_RECIPES = V15_LOCKED.contract_gap_deterministic_recipes
LOCKED_DOC_RETRIEVAL = V15_LOCKED.doc_retrieval
LOCKED_DOC_MODE = V15_LOCKED.doc_mode
LOCKED_BENCHMARK_PROMOTED_ONLY = V15_LOCKED.benchmark_promoted_only
LOCKED_JUDGE_DIAGNOSTIC = V15_LOCKED.judge_diagnostic
LOCKED_POSTTASK_MODE = V15_LOCKED.posttask_mode
LOCKED_WATCHDOG_ALLOW_POSTTASK_IN_SAFE_MODE = V15_LOCKED.watchdog_allow_posttask_in_safe_mode

DEFAULT_RUNS = 5
DEFAULT_MAX_STEPS = 4

# Pull the canonical learning root from the active runner so this wrapper
# snapshots/restores exactly what the runtime actually uses.
LEARNING_ROOT = Path(getattr(agent_cli, "LEARNING_ROOT", REPO_ROOT / "tracks" / "cli_sqlite" / "learning"))
LEARNING_MODES = tuple(getattr(agent_cli, "LEARNING_MODES", ("legacy", "strict")))
BENCHMARK_LEARNING_MODE = "strict" if "strict" in LEARNING_MODES else str(getattr(agent_cli, "DEFAULT_LEARNING_MODE", "legacy"))


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_cfg_for_openai() -> Any:
    # `load_config()` requires ANTHROPIC_API_KEY by default.
    # OpenAI runs only need OPENAI_API_KEY, so we keep parity with existing
    # wrapper scripts and allow an anthropic-empty shim.
    try:
        return load_config()
    except RuntimeError:
        return SimpleNamespace(anthropic_api_key="")


def _remove_tree_entry(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
        return
    path.unlink(missing_ok=True)


def _snapshot_learning_tree(learning_root: Path) -> Path:
    # Snapshot the entire learning tree so both arms can start from identical
    # state and the caller's pre-existing state is restored afterward.
    holder = Path(tempfile.mkdtemp(prefix="cli_sqlite_v15_learning_"))
    snapshot = holder / "snapshot"
    snapshot.mkdir(parents=True, exist_ok=True)
    if learning_root.exists():
        shutil.copytree(learning_root, snapshot, dirs_exist_ok=True)
    return holder


def _seed_empty_learning_snapshot() -> Path:
    """Create a deterministic empty learning baseline for fresh ON/OFF experiments."""
    holder = Path(tempfile.mkdtemp(prefix="cli_sqlite_v15_learning_empty_"))
    snapshot = holder / "snapshot"
    snapshot.mkdir(parents=True, exist_ok=True)
    # Seed both legacy and v2 files so downstream code never depends on
    # implicit file creation behavior.
    (snapshot / "lessons.jsonl").write_text("", encoding="utf-8")
    (snapshot / "lessons_v2.jsonl").write_text("", encoding="utf-8")
    # Benchmarks should not inherit safety streak state from earlier unrelated
    # runs. That state is product-useful, but it is a confounder for ON/OFF
    # measurement because it changes behavior for reasons unrelated to memory.
    (snapshot / "loop_watchdog_state.json").write_text(
        json.dumps(
            {
                "version": 1,
                "safe_mode_active": False,
                "safe_mode_failure_streak": 0,
                "rejection_streak": 0,
                "last_run_id": "",
                "last_failure_signals": [],
                "last_stop_flag": False,
                "updated_at_ts": 0,
            },
            ensure_ascii=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return holder


def _reset_watchdog_state(learning_root: Path) -> None:
    """Reset watchdog state between benchmark sessions.

    Why this exists:
    - The watchdog tracks repeated failures across runs.
    - That is valid for product behavior, but it contaminates benchmark runs
      when we are trying to isolate lesson memory effects.
    - We keep lessons between ON runs, but we reset watchdog streaks so each
      session starts with the same safety posture.
    """
    learning_root.mkdir(parents=True, exist_ok=True)
    (learning_root / "loop_watchdog_state.json").write_text(
        json.dumps(
            {
                "version": 1,
                "safe_mode_active": False,
                "safe_mode_failure_streak": 0,
                "rejection_streak": 0,
                "last_run_id": "",
                "last_failure_signals": [],
                "last_stop_flag": False,
                "updated_at_ts": 0,
            },
            ensure_ascii=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _restore_learning_tree(*, snapshot_holder: Path, learning_root: Path) -> None:
    snapshot = snapshot_holder / "snapshot"
    learning_root.mkdir(parents=True, exist_ok=True)

    # Remove current state first so deleted files from the baseline do not leak.
    for child in list(learning_root.iterdir()):
        _remove_tree_entry(child)

    # Recreate baseline exactly as captured.
    for child in snapshot.iterdir():
        target = learning_root / child.name
        if child.is_dir() and not child.is_symlink():
            shutil.copytree(child, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, target)


def _extract_activation(metrics: dict[str, Any]) -> float:
    # Prefer effective metrics because placebo mode can intentionally suppress
    # real lesson influence while still exercising retrieval plumbing.
    for key in (
        "v2_lesson_activations_effective",
        "v2_lesson_activations",
        "lesson_activations",
    ):
        if key in metrics:
            return _as_float(metrics.get(key, 0.0), default=0.0)
    return 0.0


def _extract_retrieval_help(metrics: dict[str, Any]) -> float:
    for key in ("v2_retrieval_help_ratio_effective", "v2_retrieval_help_ratio"):
        if key in metrics:
            return _as_float(metrics.get(key, 0.0), default=0.0)
    return 0.0


def _summarize(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    if not rows:
        return {
            "run_count": 0,
            "pass_rate": 0.0,
            "last5_pass_rate": 0.0,
            "activation_mean": 0.0,
            "retrieval_help_mean": 0.0,
        }

    run_count = len(rows)
    pass_count = sum(1 for row in rows if bool(row.get("passed", False)))
    tail = rows[-5:]
    tail_pass_count = sum(1 for row in tail if bool(row.get("passed", False)))
    activation_mean = sum(_as_float(row.get("activation", 0.0), default=0.0) for row in rows) / float(run_count)
    retrieval_help_mean = sum(_as_float(row.get("retrieval_help", 0.0), default=0.0) for row in rows) / float(run_count)
    return {
        "run_count": run_count,
        "pass_rate": round(pass_count / float(run_count), 4),
        "last5_pass_rate": round(tail_pass_count / float(len(tail)), 4),
        "activation_mean": round(activation_mean, 4),
        "retrieval_help_mean": round(retrieval_help_mean, 4),
    }


def _run_arm(
    *,
    cfg: Any,
    arm_id: str,
    task_id: str,
    domain: str,
    runs: int,
    max_steps: int,
    start_session: int,
    posttask_learn: bool,
    benchmark_placebo: bool,
    verbose: bool,
    contract_gap_retry: bool,
    contract_gap_retry_steps: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for index in range(runs):
        session_id = int(start_session) + index
        started = time.time()
        _reset_watchdog_state(LEARNING_ROOT)
        result = agent_cli.run_cli_agent(
            cfg=cfg,
            task_id=task_id,
            task=None,
            session_id=session_id,
            max_steps=int(max_steps),
            domain=domain,
            learning_mode=BENCHMARK_LEARNING_MODE,
            model_executor=LOCKED_MODEL_EXECUTOR,
            model_critic=LOCKED_MODEL_CRITIC,
            model_judge=LOCKED_MODEL_JUDGE,
            posttask_mode=LOCKED_POSTTASK_MODE,
            posttask_learn=bool(posttask_learn),
            self_edit_mode=LOCKED_SELF_EDIT_MODE,
            verbose=bool(verbose),
            auto_escalate_critic=False,
            escalation_score_threshold=0.75,
            escalation_consecutive_runs=2,
            require_skill_read=True,
            opaque_tools=False,
            bootstrap=False,
            cryptic_errors=False,
            semi_helpful_errors=False,
            mixed_errors=False,
            documentation=[],
            doc_mode=LOCKED_DOC_MODE,
            doc_budget_tokens=900,
            doc_retrieval=LOCKED_DOC_RETRIEVAL,
            doc_retriever_model=None,
            judge_docs=False,
            executor_docs=False,
            judge_diagnostic=LOCKED_JUDGE_DIAGNOSTIC,
            contract_gap_retry=bool(contract_gap_retry),
            contract_gap_retry_steps=max(0, int(contract_gap_retry_steps)),
            contract_gap_deterministic_recipes=LOCKED_CONTRACT_GAP_DETERMINISTIC_RECIPES,
            structured_lessons_required=LOCKED_STRUCTURED_LESSONS_REQUIRED,
            llm_backend=LOCKED_BACKEND,
            benchmark_deterministic=LOCKED_BENCHMARK_DETERMINISTIC,
            benchmark_promoted_only=LOCKED_BENCHMARK_PROMOTED_ONLY,
            benchmark_placebo=bool(benchmark_placebo),
            watchdog_allow_posttask_in_safe_mode=LOCKED_WATCHDOG_ALLOW_POSTTASK_IN_SAFE_MODE,
        )

        metrics = dict(result.metrics or {})
        _assert_locked_metrics(
            metrics=metrics,
            arm_id=arm_id,
            expected_contract_gap_retry=bool(contract_gap_retry),
        )
        row = {
            "arm": arm_id,
            "run_index": index + 1,
            "session_id": session_id,
            "passed": bool(metrics.get("eval_passed", False)),
            "score": round(_as_float(metrics.get("eval_score", 0.0), default=0.0), 4),
            "activation": round(_extract_activation(metrics), 4),
            "retrieval_help": round(_extract_retrieval_help(metrics), 4),
            "elapsed_s": round(time.time() - started, 3),
        }
        rows.append(row)

        status = "PASS" if row["passed"] else "FAIL"
        print(
            f"[{arm_id}] run={row['run_index']}/{runs} "
            f"session={row['session_id']} {status} score={row['score']:.2f} "
            f"act={row['activation']:.2f} help={row['retrieval_help']:.2f} "
            f"time={row['elapsed_s']:.2f}s"
        )

    return rows


def _assert_locked_metrics(*, metrics: dict[str, Any], arm_id: str, expected_contract_gap_retry: bool) -> None:
    """Fail fast if runtime drifted away from locked v1.5 policy."""
    backend = str(metrics.get("llm_backend") or "").strip()
    critic_model = str(metrics.get("critic_model") or "").strip()
    if backend and backend != LOCKED_BACKEND:
        raise RuntimeError(f"[{arm_id}] backend drift: expected={LOCKED_BACKEND} got={backend}")
    if critic_model and critic_model != LOCKED_MODEL_CRITIC:
        raise RuntimeError(f"[{arm_id}] critic model drift: expected={LOCKED_MODEL_CRITIC} got={critic_model}")
    if bool(metrics.get("benchmark_deterministic")) != LOCKED_BENCHMARK_DETERMINISTIC:
        raise RuntimeError(
            f"[{arm_id}] benchmark_deterministic drift: expected={LOCKED_BENCHMARK_DETERMINISTIC} "
            f"got={metrics.get('benchmark_deterministic')}"
        )
    if bool(metrics.get("benchmark_promoted_only")) != LOCKED_BENCHMARK_PROMOTED_ONLY:
        raise RuntimeError(
            f"[{arm_id}] benchmark_promoted_only drift: expected={LOCKED_BENCHMARK_PROMOTED_ONLY} "
            f"got={metrics.get('benchmark_promoted_only')}"
        )
    # Some policy fields are enforced but not surfaced as top-level metrics in
    # current runtime output; assertions here only cover emitted keys.
    if bool(metrics.get("contract_gap_retry_enabled")) != bool(expected_contract_gap_retry):
        raise RuntimeError(
            f"[{arm_id}] contract_gap_retry drift: expected={bool(expected_contract_gap_retry)} "
            f"got={metrics.get('contract_gap_retry_enabled')}"
        )
    if bool(metrics.get("contract_gap_deterministic_recipes_enabled")) != LOCKED_CONTRACT_GAP_DETERMINISTIC_RECIPES:
        raise RuntimeError(
            f"[{arm_id}] contract_gap_deterministic_recipes drift: "
            f"expected={LOCKED_CONTRACT_GAP_DETERMINISTIC_RECIPES} "
            f"got={metrics.get('contract_gap_deterministic_recipes_enabled')}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run minimal v1.5 ON/OFF smoke benchmark with locked flags.")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--domain", default="gridtool", choices=["sqlite", "gridtool", "fluxtool", "artic", "shell"])
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
    parser.add_argument("--start-session-on", required=True, type=int)
    parser.add_argument("--start-session-off", required=True, type=int)
    parser.add_argument(
        "--fresh-learning-state",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Start both arms from empty lessons files (default: true).",
    )
    parser.add_argument(
        "--contract-gap-retry-mode",
        choices=["locked", "on", "off"],
        default="locked",
        help="Experimental proof override. 'locked' keeps v1.5 default; 'off' disables contract-gap retry for both arms.",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if int(args.runs) <= 0:
        raise ValueError("--runs must be >= 1")
    if int(args.max_steps) <= 0:
        raise ValueError("--max-steps must be >= 1")

    effective_contract_gap_retry = LOCKED_CONTRACT_GAP_RETRY
    effective_contract_gap_retry_steps = LOCKED_CONTRACT_GAP_RETRY_STEPS
    if str(args.contract_gap_retry_mode).strip() == "on":
        effective_contract_gap_retry = True
        effective_contract_gap_retry_steps = max(1, int(LOCKED_CONTRACT_GAP_RETRY_STEPS))
    elif str(args.contract_gap_retry_mode).strip() == "off":
        effective_contract_gap_retry = False
        effective_contract_gap_retry_steps = 0

    cfg = _load_cfg_for_openai()
    baseline_holder = (
        _seed_empty_learning_snapshot()
        if bool(args.fresh_learning_state)
        else _snapshot_learning_tree(LEARNING_ROOT)
    )

    off_rows: list[dict[str, Any]] = []
    on_rows: list[dict[str, Any]] = []
    try:
        # OFF arm: no posttask learning writes + placebo retrieval text.
        _restore_learning_tree(snapshot_holder=baseline_holder, learning_root=LEARNING_ROOT)
        off_rows = _run_arm(
            cfg=cfg,
            arm_id="off",
            task_id=args.task_id,
            domain=args.domain,
            runs=int(args.runs),
            max_steps=int(args.max_steps),
            start_session=int(args.start_session_off),
            posttask_learn=False,
            benchmark_placebo=True,
            verbose=bool(args.verbose),
            contract_gap_retry=effective_contract_gap_retry,
            contract_gap_retry_steps=effective_contract_gap_retry_steps,
        )

        # ON arm: same baseline, same locked runtime, learning enabled.
        _restore_learning_tree(snapshot_holder=baseline_holder, learning_root=LEARNING_ROOT)
        on_rows = _run_arm(
            cfg=cfg,
            arm_id="on",
            task_id=args.task_id,
            domain=args.domain,
            runs=int(args.runs),
            max_steps=int(args.max_steps),
            start_session=int(args.start_session_on),
            posttask_learn=True,
            benchmark_placebo=False,
            verbose=bool(args.verbose),
            contract_gap_retry=effective_contract_gap_retry,
            contract_gap_retry_steps=effective_contract_gap_retry_steps,
        )
    finally:
        # Always restore caller state even on crash/interrupt.
        _restore_learning_tree(snapshot_holder=baseline_holder, learning_root=LEARNING_ROOT)
        shutil.rmtree(baseline_holder, ignore_errors=True)

    off_summary = _summarize(off_rows)
    on_summary = _summarize(on_rows)
    payload = {
        "config": {
            "task_id": str(args.task_id),
            "domain": str(args.domain),
            "runs": int(args.runs),
            "max_steps": int(args.max_steps),
            "fresh_learning_state": bool(args.fresh_learning_state),
            "start_session_off": int(args.start_session_off),
            "start_session_on": int(args.start_session_on),
            "locked": {
                "backend": LOCKED_BACKEND,
                "model_executor": LOCKED_MODEL_EXECUTOR,
                "model_judge": LOCKED_MODEL_JUDGE,
                "self_edit_mode": LOCKED_SELF_EDIT_MODE,
                "benchmark_deterministic": LOCKED_BENCHMARK_DETERMINISTIC,
                "structured_lessons_required": LOCKED_STRUCTURED_LESSONS_REQUIRED,
                "contract_gap_retry": bool(effective_contract_gap_retry),
                "contract_gap_retry_mode": str(args.contract_gap_retry_mode),
                "contract_gap_deterministic_recipes": LOCKED_CONTRACT_GAP_DETERMINISTIC_RECIPES,
                "doc_retrieval": LOCKED_DOC_RETRIEVAL,
                "doc_mode": LOCKED_DOC_MODE,
                "benchmark_promoted_only": LOCKED_BENCHMARK_PROMOTED_ONLY,
                "judge_diagnostic": LOCKED_JUDGE_DIAGNOSTIC,
                "watchdog_allow_posttask_in_safe_mode": LOCKED_WATCHDOG_ALLOW_POSTTASK_IN_SAFE_MODE,
            },
            "off_arm": {
                "no_posttask_learn": True,
                "benchmark_placebo": True,
            },
            "on_arm": {
                "no_posttask_learn": False,
                "benchmark_placebo": False,
            },
        },
        "off": off_summary,
        "on": on_summary,
        "delta_on_minus_off": {
            "pass_rate": round(_as_float(on_summary.get("pass_rate", 0.0)) - _as_float(off_summary.get("pass_rate", 0.0)), 4),
            "last5_pass_rate": round(
                _as_float(on_summary.get("last5_pass_rate", 0.0)) - _as_float(off_summary.get("last5_pass_rate", 0.0)),
                4,
            ),
            "activation_mean": round(
                _as_float(on_summary.get("activation_mean", 0.0)) - _as_float(off_summary.get("activation_mean", 0.0)),
                4,
            ),
            "retrieval_help_mean": round(
                _as_float(on_summary.get("retrieval_help_mean", 0.0)) - _as_float(off_summary.get("retrieval_help_mean", 0.0)),
                4,
            ),
        },
    }

    # Compact JSON output for easy piping and machine parsing.
    print(json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
