#!/usr/bin/env python3
"""Run N sequential sessions to measure the learning curve.

Usage:
  python3 tracks/cli_sqlite/scripts/run_learning_curve.py \
    --task-id aggregate_report --domain gridtool --sessions 5 \
    --bootstrap --start-session 9001 --verbose

Outputs a summary table of scores across sessions.
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Run N sessions and plot the learning curve")
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--domain", default="gridtool", choices=["sqlite", "gridtool"])
    ap.add_argument("--sessions", type=int, default=5, help="Number of sequential sessions")
    ap.add_argument("--start-session", type=int, default=9001, help="Starting session ID")
    ap.add_argument("--max-steps", type=int, default=12)
    ap.add_argument("--bootstrap", action="store_true", help="No skill docs, lessons only")
    ap.add_argument("--cryptic-errors", action="store_true", help="Cryptic errors: strip hints from error messages")
    ap.add_argument("--model-executor", default=DEFAULT_EXECUTOR_MODEL)
    ap.add_argument("--model-critic", default=DEFAULT_CRITIC_MODEL)
    ap.add_argument("--model-judge", default=None)
    ap.add_argument("--posttask-mode", choices=["candidate", "direct"], default="direct")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    results: list[dict] = []

    print(f"\n{'='*60}")
    print(f"  Learning Curve Experiment")
    print(f"  task={args.task_id}  domain={args.domain}  bootstrap={args.bootstrap}")
    print(f"  cryptic_errors={args.cryptic_errors}  sessions={args.sessions}  model={args.model_executor}")
    print(f"{'='*60}\n")

    for i in range(args.sessions):
        session_id = args.start_session + i
        run_num = i + 1
        print(f"--- Run {run_num}/{args.sessions} (session {session_id}) ---")
        t0 = time.time()

        result = run_cli_agent(
            cfg=cfg,
            task_id=args.task_id,
            task=None,
            session_id=session_id,
            max_steps=args.max_steps,
            domain=args.domain,
            model_executor=args.model_executor.strip() or DEFAULT_EXECUTOR_MODEL,
            model_critic=args.model_critic.strip() or DEFAULT_CRITIC_MODEL,
            model_judge=args.model_judge.strip() if args.model_judge else None,
            posttask_mode=args.posttask_mode,
            posttask_learn=True,
            verbose=args.verbose,
            auto_escalate_critic=True,
            escalation_score_threshold=0.75,
            escalation_consecutive_runs=2,
            require_skill_read=not args.bootstrap,
            opaque_tools=False,
            bootstrap=args.bootstrap,
            cryptic_errors=args.cryptic_errors,
        )

        m = result.metrics
        elapsed = time.time() - t0
        row = {
            "run": run_num,
            "session_id": session_id,
            "score": m.get("eval_score", 0.0),
            "passed": m.get("eval_passed", False),
            "steps": m.get("steps", 0),
            "tool_errors": m.get("tool_errors", 0),
            "lessons_loaded": m.get("lessons_loaded", 0),
            "lessons_generated": m.get("lessons_generated", 0),
            "elapsed_s": round(elapsed, 1),
        }
        results.append(row)

        status = "PASS" if row["passed"] else "FAIL"
        print(f"  [{status}] score={row['score']:.2f}  steps={row['steps']}  "
              f"errors={row['tool_errors']}  lessons_in={row['lessons_loaded']}  "
              f"lessons_out={row['lessons_generated']}  ({row['elapsed_s']}s)")
        print()

    # Summary table
    print(f"\n{'='*60}")
    print(f"  LEARNING CURVE SUMMARY")
    print(f"{'='*60}")
    print(f"{'Run':>4} {'Session':>8} {'Score':>6} {'Pass':>5} {'Steps':>6} {'Errs':>5} {'LessIn':>7} {'LessOut':>8} {'Time':>6}")
    print(f"{'-'*4:>4} {'-'*8:>8} {'-'*6:>6} {'-'*5:>5} {'-'*6:>6} {'-'*5:>5} {'-'*7:>7} {'-'*8:>8} {'-'*6:>6}")
    for r in results:
        status = "Y" if r["passed"] else "N"
        print(f"{r['run']:>4} {r['session_id']:>8} {r['score']:>6.2f} {status:>5} "
              f"{r['steps']:>6} {r['tool_errors']:>5} {r['lessons_loaded']:>7} "
              f"{r['lessons_generated']:>8} {r['elapsed_s']:>5.1f}s")

    scores = [r["score"] for r in results]
    print(f"\nScore trajectory: {' -> '.join(f'{s:.2f}' for s in scores)}")
    if len(scores) >= 2:
        delta = scores[-1] - scores[0]
        print(f"Improvement: {scores[0]:.2f} -> {scores[-1]:.2f} (delta={delta:+.2f})")
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
