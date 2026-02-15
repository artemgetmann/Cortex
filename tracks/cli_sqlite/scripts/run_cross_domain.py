#!/usr/bin/env python3
"""Run cross-domain transfer experiment (train on one domain, test on another)."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from config import load_config
from tracks.cli_sqlite.agent_cli import (
    DEFAULT_CRITIC_MODEL,
    DEFAULT_EXECUTOR_MODEL,
    DEFAULT_LEARNING_MODE,
    LEARNING_MODES,
    run_cli_agent,
)


LEARNING_ROOT = Path(__file__).resolve().parents[1] / "learning"
LESSONS_PATH = LEARNING_ROOT / "lessons.jsonl"
ESCALATION_PATH = LEARNING_ROOT / "critic_escalation_state.json"


def _clear_escalation() -> None:
    if ESCALATION_PATH.exists():
        ESCALATION_PATH.unlink()


def _clear_lessons() -> None:
    LEARNING_ROOT.mkdir(parents=True, exist_ok=True)
    LESSONS_PATH.write_text("", encoding="utf-8")


def _run_phase(
    *,
    cfg,
    phase: str,
    domain: str,
    task_id: str,
    n_sessions: int,
    start_session: int,
    max_steps: int,
    learning_mode: str,
    model_executor: str,
    model_critic: str,
    model_judge: str | None,
    posttask_mode: str,
    bootstrap: bool,
    cryptic_errors: bool,
    semi_helpful_errors: bool,
    mixed_errors: bool,
    verbose: bool,
) -> list[dict]:
    rows: list[dict] = []
    for i in range(n_sessions):
        session_id = start_session + i
        run_idx = i + 1
        print(f"  [{phase}] run {run_idx}/{n_sessions} session={session_id} domain={domain} task={task_id}")
        t0 = time.time()
        result = run_cli_agent(
            cfg=cfg,
            task_id=task_id,
            task=None,
            session_id=session_id,
            max_steps=max_steps,
            domain=domain,
            learning_mode=learning_mode,
            model_executor=model_executor,
            model_critic=model_critic,
            model_judge=model_judge,
            posttask_mode=posttask_mode,
            posttask_learn=True,
            verbose=verbose,
            auto_escalate_critic=True,
            escalation_score_threshold=0.75,
            escalation_consecutive_runs=2,
            require_skill_read=not bootstrap,
            opaque_tools=False,
            bootstrap=bootstrap,
            cryptic_errors=cryptic_errors,
            semi_helpful_errors=semi_helpful_errors,
            mixed_errors=mixed_errors,
        )

        m = result.metrics
        elapsed = time.time() - t0
        row = {
            "phase": phase,
            "domain": domain,
            "task_id": task_id,
            "run": run_idx,
            "session_id": session_id,
            "score": float(m.get("eval_score", 0.0) or 0.0),
            "passed": bool(m.get("eval_passed", False)),
            "steps": int(m.get("steps", 0) or 0),
            "tool_errors": int(m.get("tool_errors", 0) or 0),
            "lessons_loaded": int(m.get("lessons_loaded", 0) or 0),
            "lessons_generated": int(m.get("lessons_generated", 0) or 0),
            "lesson_activations": int(m.get("lesson_activations", 0) or 0),
            "elapsed_s": round(elapsed, 2),
        }
        rows.append(row)
        status = "PASS" if row["passed"] else "FAIL"
        print(
            f"    [{status}] score={row['score']:.2f} steps={row['steps']} errors={row['tool_errors']} "
            f"lessons_in={row['lessons_loaded']} lessons_out={row['lessons_generated']} "
            f"hints={row['lesson_activations']} ({row['elapsed_s']}s)"
        )
    return rows


def _transfer_metrics(test_rows: list[dict]) -> dict[str, float | int]:
    scores = [float(r["score"]) for r in test_rows]
    passes = [bool(r["passed"]) for r in test_rows]
    first_pass_index = -1
    for i, ok in enumerate(passes, start=1):
        if ok:
            first_pass_index = i
            break
    regressions = 0
    if first_pass_index != -1:
        regressions = sum(1 for ok in passes[first_pass_index:] if not ok)
    delta = 0.0
    if scores:
        delta = scores[-1] - scores[0]
    return {
        "first_pass_index": first_pass_index,
        "post_pass_regressions": regressions,
        "delta": round(delta, 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Cross-domain transfer experiment")
    ap.add_argument("--train-domain", default="gridtool", choices=["sqlite", "gridtool", "fluxtool"])
    ap.add_argument("--test-domain", default="fluxtool", choices=["sqlite", "gridtool", "fluxtool"])
    ap.add_argument("--train-task-id", default="aggregate_report")
    ap.add_argument("--test-task-id", default="aggregate_report_holdout")
    ap.add_argument("--train-sessions", type=int, default=3)
    ap.add_argument("--test-sessions", type=int, default=5)
    ap.add_argument("--start-session", type=int, default=12001)
    ap.add_argument("--max-steps", type=int, default=8)
    ap.add_argument("--learning-mode", default=DEFAULT_LEARNING_MODE, choices=LEARNING_MODES)
    ap.add_argument("--bootstrap", action="store_true")
    ap.add_argument("--cryptic-errors", action="store_true")
    ap.add_argument("--semi-helpful-errors", action="store_true")
    ap.add_argument("--mixed-errors", action="store_true")
    ap.add_argument("--model-executor", default=DEFAULT_EXECUTOR_MODEL)
    ap.add_argument("--model-critic", default=DEFAULT_CRITIC_MODEL)
    ap.add_argument("--model-judge", default=None)
    ap.add_argument("--posttask-mode", choices=["candidate", "direct"], default="direct")
    ap.add_argument("--clear-lessons", action="store_true")
    ap.add_argument("--no-train", action="store_true", help="Skip train phase to capture baseline.")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    _clear_escalation()
    if args.clear_lessons:
        _clear_lessons()

    print(f"\n{'=' * 72}")
    print("  Cross-Domain Transfer Experiment")
    print(f"  train={args.train_domain}:{args.train_task_id}  test={args.test_domain}:{args.test_task_id}")
    print(f"  learning_mode={args.learning_mode}  bootstrap={args.bootstrap}  max_steps={args.max_steps}")
    print(f"{'=' * 72}\n")

    session_cursor = args.start_session
    all_rows: list[dict] = []

    if not args.no_train:
        print(f"--- TRAIN phase ({args.train_sessions} sessions) ---")
        train_rows = _run_phase(
            cfg=cfg,
            phase="TRAIN",
            domain=args.train_domain,
            task_id=args.train_task_id,
            n_sessions=args.train_sessions,
            start_session=session_cursor,
            max_steps=args.max_steps,
            learning_mode=args.learning_mode,
            model_executor=args.model_executor.strip() or DEFAULT_EXECUTOR_MODEL,
            model_critic=args.model_critic.strip() or DEFAULT_CRITIC_MODEL,
            model_judge=args.model_judge.strip() if args.model_judge else None,
            posttask_mode=args.posttask_mode,
            bootstrap=args.bootstrap,
            cryptic_errors=args.cryptic_errors,
            semi_helpful_errors=args.semi_helpful_errors,
            mixed_errors=args.mixed_errors,
            verbose=args.verbose,
        )
        all_rows.extend(train_rows)
        session_cursor += args.train_sessions
        print()

    print(f"--- TEST phase ({args.test_sessions} sessions) ---")
    test_rows = _run_phase(
        cfg=cfg,
        phase="TEST" if not args.no_train else "BASELINE",
        domain=args.test_domain,
        task_id=args.test_task_id,
        n_sessions=args.test_sessions,
        start_session=session_cursor,
        max_steps=args.max_steps,
        learning_mode=args.learning_mode,
        model_executor=args.model_executor.strip() or DEFAULT_EXECUTOR_MODEL,
        model_critic=args.model_critic.strip() or DEFAULT_CRITIC_MODEL,
        model_judge=args.model_judge.strip() if args.model_judge else None,
        posttask_mode=args.posttask_mode,
        bootstrap=args.bootstrap,
        cryptic_errors=args.cryptic_errors,
        semi_helpful_errors=args.semi_helpful_errors,
        mixed_errors=args.mixed_errors,
        verbose=args.verbose,
    )
    all_rows.extend(test_rows)

    transfer = _transfer_metrics(test_rows)
    print(f"\n{'=' * 72}")
    print("  Transfer Summary")
    print(f"{'=' * 72}")
    print(
        f"  first_pass_index={transfer['first_pass_index']}  "
        f"post_pass_regressions={transfer['post_pass_regressions']}  "
        f"delta={float(transfer['delta']):+.2f}"
    )

    print("\n  Run table:")
    print(
        f"{'Phase':<9} {'Domain':<10} {'Task':<24} {'Run':>4} {'Score':>6} {'Pass':>5} "
        f"{'Steps':>5} {'Errs':>5} {'LessIn':>7} {'LessOut':>8} {'Hints':>6}"
    )
    for row in all_rows:
        p = "Y" if row["passed"] else "N"
        print(
            f"{row['phase']:<9} {row['domain']:<10} {row['task_id']:<24} {row['run']:>4} {row['score']:>6.2f} {p:>5} "
            f"{row['steps']:>5} {row['tool_errors']:>5} {row['lessons_loaded']:>7} "
            f"{row['lessons_generated']:>8} {row['lesson_activations']:>6}"
        )

    payload = {
        "config": {
            "train_domain": args.train_domain,
            "test_domain": args.test_domain,
            "train_task_id": args.train_task_id,
            "test_task_id": args.test_task_id,
            "learning_mode": args.learning_mode,
            "bootstrap": args.bootstrap,
            "max_steps": args.max_steps,
        },
        "transfer": transfer,
        "runs": all_rows,
    }
    print("\nJSON summary:")
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
