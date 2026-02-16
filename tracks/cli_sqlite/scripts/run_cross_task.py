#!/usr/bin/env python3
"""Run cross-task transfer experiment: train on task A, test on task B.

Demonstrates that lessons learned from one gridtool task help on a different task.

Usage:
  # Phase 1: Train on aggregate_report (accumulate lessons)
  # Phase 2: Test on basic_transform and multi_step_pipeline (transfer)
  python3 tracks/cli_sqlite/scripts/run_cross_task.py \
    --train-task aggregate_report --test-tasks basic_transform multi_step_pipeline \
    --domain gridtool --train-sessions 3 --test-sessions 5 \
    --start-session 11001 --max-steps 3 --bootstrap --semi-helpful-errors --verbose
"""
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
    run_cli_agent,
)

LEARNING_ROOT = Path(__file__).resolve().parents[1] / "learning"
LESSONS_PATH = LEARNING_ROOT / "lessons.jsonl"
ESCALATION_PATH = LEARNING_ROOT / "critic_escalation_state.json"


def _clear_escalation():
    if ESCALATION_PATH.exists():
        ESCALATION_PATH.unlink()


def _run_phase(
    *,
    cfg,
    task_id: str,
    phase_name: str,
    n_sessions: int,
    start_session: int,
    max_steps: int,
    domain: str,
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
    results = []
    for i in range(n_sessions):
        session_id = start_session + i
        run_num = i + 1
        print(f"  [{phase_name}] Run {run_num}/{n_sessions} (session {session_id}, task={task_id})")
        t0 = time.time()

        result = run_cli_agent(
            cfg=cfg,
            task_id=task_id,
            task=None,
            session_id=session_id,
            max_steps=max_steps,
            domain=domain,
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
            "phase": phase_name,
            "task_id": task_id,
            "run": run_num,
            "session_id": session_id,
            "score": m.get("eval_score", 0.0),
            "passed": m.get("eval_passed", False),
            "steps": m.get("steps", 0),
            "tool_errors": m.get("tool_errors", 0),
            "lessons_loaded": m.get("lessons_loaded", 0),
            "lessons_generated": m.get("lessons_generated", 0),
            "lesson_activations": m.get("lesson_activations", 0),
            "elapsed_s": round(elapsed, 1),
        }
        results.append(row)

        status = "PASS" if row["passed"] else "FAIL"
        print(f"    [{status}] score={row['score']:.2f}  steps={row['steps']}  "
              f"errors={row['tool_errors']}  lessons_in={row['lessons_loaded']}  "
              f"lessons_out={row['lessons_generated']}  hints={row['lesson_activations']}  "
              f"({row['elapsed_s']}s)")

    return results


def _count_lessons() -> int:
    if not LESSONS_PATH.exists():
        return 0
    return sum(1 for line in LESSONS_PATH.read_text().splitlines() if line.strip())


def main() -> int:
    ap = argparse.ArgumentParser(description="Cross-task transfer experiment")
    ap.add_argument("--train-task", required=True, help="Task to train on first")
    ap.add_argument("--test-tasks", nargs="+", required=True, help="Tasks to test transfer on")
    ap.add_argument("--domain", default="gridtool", choices=["sqlite", "gridtool", "fluxtool", "artic"])
    ap.add_argument("--train-sessions", type=int, default=3, help="Training sessions on source task")
    ap.add_argument("--test-sessions", type=int, default=5, help="Test sessions per target task")
    ap.add_argument("--start-session", type=int, default=11001, help="Starting session ID")
    ap.add_argument("--max-steps", type=int, default=3)
    ap.add_argument("--bootstrap", action="store_true")
    ap.add_argument("--cryptic-errors", action="store_true")
    ap.add_argument("--semi-helpful-errors", action="store_true")
    ap.add_argument("--mixed-errors", action="store_true",
                    help="Mixed mode: semi-helpful for simple commands, cryptic for core pipeline commands")
    ap.add_argument("--model-executor", default=DEFAULT_EXECUTOR_MODEL)
    ap.add_argument("--model-critic", default=DEFAULT_CRITIC_MODEL)
    ap.add_argument("--model-judge", default=None)
    ap.add_argument("--posttask-mode", choices=["candidate", "direct"], default="direct")
    ap.add_argument("--verbose", action="store_true")
    # Control experiment: skip training phase to establish baseline
    ap.add_argument("--no-train", action="store_true",
                    help="Skip training phase (control experiment for baseline comparison)")
    args = ap.parse_args()

    cfg = load_config()
    _clear_escalation()

    all_results: list[dict] = []
    session_cursor = args.start_session

    print(f"\n{'='*70}")
    print(f"  Cross-Task Transfer Experiment")
    print(f"  train={args.train_task}  test={args.test_tasks}")
    print(f"  domain={args.domain}  bootstrap={args.bootstrap}  max_steps={args.max_steps}")
    print(f"  semi_helpful={args.semi_helpful_errors}  mixed_errors={args.mixed_errors}  model={args.model_executor}")
    if args.no_train:
        print(f"  ** CONTROL: no training phase (baseline) **")
    print(f"{'='*70}\n")

    # Phase 1: Training
    if not args.no_train:
        print(f"--- PHASE 1: TRAINING on '{args.train_task}' ({args.train_sessions} sessions) ---")
        print(f"    Lessons before training: {_count_lessons()}")
        train_results = _run_phase(
            cfg=cfg,
            task_id=args.train_task,
            phase_name="TRAIN",
            n_sessions=args.train_sessions,
            start_session=session_cursor,
            max_steps=args.max_steps,
            domain=args.domain,
            model_executor=args.model_executor,
            model_critic=args.model_critic,
            model_judge=args.model_judge,
            posttask_mode=args.posttask_mode,
            bootstrap=args.bootstrap,
            cryptic_errors=args.cryptic_errors,
            semi_helpful_errors=args.semi_helpful_errors,
            mixed_errors=args.mixed_errors,
            verbose=args.verbose,
        )
        all_results.extend(train_results)
        session_cursor += args.train_sessions
        print(f"    Lessons after training: {_count_lessons()}\n")

    # Phase 2: Testing on each target task
    for test_task in args.test_tasks:
        phase_label = "TEST" if not args.no_train else "BASELINE"
        print(f"--- PHASE 2: {phase_label} on '{test_task}' ({args.test_sessions} sessions) ---")
        print(f"    Lessons available: {_count_lessons()}")
        test_results = _run_phase(
            cfg=cfg,
            task_id=test_task,
            phase_name=phase_label,
            n_sessions=args.test_sessions,
            start_session=session_cursor,
            max_steps=args.max_steps,
            domain=args.domain,
            model_executor=args.model_executor,
            model_critic=args.model_critic,
            model_judge=args.model_judge,
            posttask_mode=args.posttask_mode,
            bootstrap=args.bootstrap,
            cryptic_errors=args.cryptic_errors,
            semi_helpful_errors=args.semi_helpful_errors,
            mixed_errors=args.mixed_errors,
            verbose=args.verbose,
        )
        all_results.extend(test_results)
        session_cursor += args.test_sessions
        print()

    # Summary
    print(f"\n{'='*70}")
    print(f"  CROSS-TASK TRANSFER SUMMARY")
    print(f"{'='*70}")
    print(f"{'Phase':<10} {'Task':<22} {'Run':>4} {'Score':>6} {'Pass':>5} {'Steps':>6} "
          f"{'Errs':>5} {'LessIn':>7} {'LessOut':>8} {'Hints':>6}")
    print(f"{'-'*10:<10} {'-'*22:<22} {'-'*4:>4} {'-'*6:>6} {'-'*5:>5} {'-'*6:>6} "
          f"{'-'*5:>5} {'-'*7:>7} {'-'*8:>8} {'-'*6:>6}")
    for r in all_results:
        status = "Y" if r["passed"] else "N"
        print(f"{r['phase']:<10} {r['task_id']:<22} {r['run']:>4} {r['score']:>6.2f} "
              f"{status:>5} {r['steps']:>6} {r['tool_errors']:>5} {r['lessons_loaded']:>7} "
              f"{r['lessons_generated']:>8} {r['lesson_activations']:>6}")

    # Per-task score summary
    print(f"\n--- Score by task ---")
    tasks_seen = []
    for r in all_results:
        key = (r["phase"], r["task_id"])
        if key not in tasks_seen:
            tasks_seen.append(key)

    for phase, task_id in tasks_seen:
        task_results = [r for r in all_results if r["phase"] == phase and r["task_id"] == task_id]
        scores = [r["score"] for r in task_results]
        first_score = scores[0] if scores else 0.0
        last_score = scores[-1] if scores else 0.0
        avg_score = sum(scores) / len(scores) if scores else 0.0
        print(f"  [{phase}] {task_id}: {' -> '.join(f'{s:.2f}' for s in scores)}  "
              f"(avg={avg_score:.2f}, delta={last_score - first_score:+.2f})")

    # Transfer effectiveness
    if not args.no_train:
        print(f"\n--- Transfer Effectiveness ---")
        train_scores = [r["score"] for r in all_results if r["phase"] == "TRAIN"]
        for test_task in args.test_tasks:
            test_scores = [r["score"] for r in all_results
                          if r["phase"] == "TEST" and r["task_id"] == test_task]
            if test_scores:
                first_test = test_scores[0]
                print(f"  {test_task}: first-test-score={first_test:.2f} "
                      f"(with {_count_lessons()} lessons from training)")
                if first_test >= 0.75:
                    print(f"    -> POSITIVE TRANSFER: lessons from {args.train_task} helped!")
                elif first_test >= 0.25:
                    print(f"    -> PARTIAL TRANSFER: some benefit from prior lessons")
                else:
                    print(f"    -> NO TRANSFER: prior lessons didn't help on first attempt")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
