#!/usr/bin/env python3
"""Cortex CLI Learning Demo — Rich terminal visualization of agent learning."""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from config import load_config
from tracks.cli_sqlite.agent_cli import (
    DEFAULT_EXECUTOR_MODEL,
    DEFAULT_CRITIC_MODEL,
    LESSONS_PATH,
    run_cli_agent,
)
from tracks.cli_sqlite.demo_display import (
    console,
    show_demo_header,
    show_final_summary,
    show_learning_progress,
    show_lessons_generated,
    show_session_header,
    show_session_replay,
    show_session_score,
    show_step,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Cortex CLI Learning Demo")
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--domain", default="gridtool", choices=["sqlite", "gridtool"])
    ap.add_argument("--sessions", type=int, default=6)
    ap.add_argument("--start-session", type=int, default=10001)
    ap.add_argument("--max-steps", type=int, default=12)
    ap.add_argument("--model-executor", default=DEFAULT_EXECUTOR_MODEL)
    ap.add_argument("--model-critic", default=DEFAULT_CRITIC_MODEL)
    ap.add_argument("--model-judge", default=None)
    ap.add_argument("--bootstrap", action="store_true")
    ap.add_argument("--cryptic-errors", action="store_true")
    ap.add_argument("--semi-helpful-errors", action="store_true")
    ap.add_argument("--clear-lessons", action="store_true", help="Clear lessons before starting")
    ap.add_argument("--replay-detail", choices=["full", "compact", "none"], default="compact")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    model = args.model_executor.strip() or DEFAULT_EXECUTOR_MODEL

    # Clear escalation state for clean experiment
    escalation_path = Path(__file__).resolve().parents[1] / "learning" / "critic_escalation_state.json"
    if escalation_path.exists():
        escalation_path.unlink()

    # Clear lessons if requested
    if args.clear_lessons and LESSONS_PATH.exists():
        shutil.copy2(LESSONS_PATH, LESSONS_PATH.with_suffix(".jsonl.bak"))
        LESSONS_PATH.write_text("")
        console.print("[yellow]  Lessons cleared (backup saved)[/yellow]")

    show_demo_header(args.task_id, model, args.sessions, args.domain)

    results: list[dict] = []
    scores: list[float] = []

    for i in range(args.sessions):
        session_id = args.start_session + i
        run_num = i + 1

        # Count lessons
        lesson_count = 0
        if LESSONS_PATH.exists() and LESSONS_PATH.stat().st_size > 0:
            lesson_count = sum(1 for _ in open(LESSONS_PATH))

        show_session_header(run_num, args.sessions, session_id, lesson_count)

        t0 = time.time()
        result = run_cli_agent(
            cfg=cfg,
            task_id=args.task_id,
            task=None,
            session_id=session_id,
            max_steps=args.max_steps,
            domain=args.domain,
            model_executor=model,
            model_critic=args.model_critic.strip() or DEFAULT_CRITIC_MODEL,
            model_judge=args.model_judge.strip() if args.model_judge else None,
            posttask_mode="direct",
            posttask_learn=True,
            verbose=args.verbose,
            auto_escalate_critic=True,
            require_skill_read=not args.bootstrap,
            bootstrap=args.bootstrap,
            cryptic_errors=args.cryptic_errors,
            semi_helpful_errors=args.semi_helpful_errors,
            on_step=show_step,
        )
        elapsed = time.time() - t0

        m = result.metrics

        # Show replay
        if args.replay_detail != "none":
            show_session_replay(result.messages, detail=args.replay_detail)

        # Extract scores — prefer eval, fall back to judge
        score = float(m.get("eval_score", 0) or 0)
        passed = bool(m.get("eval_passed", False))
        reasons = m.get("eval_reasons") or m.get("judge_reasons")

        show_session_score(score, passed, reasons)
        show_lessons_generated(m.get("lessons_generated", 0))

        scores.append(score)
        show_learning_progress(scores)

        results.append({
            "run": run_num,
            "session_id": session_id,
            "score": score,
            "passed": passed,
            "steps": m.get("steps", 0),
            "tool_errors": m.get("tool_errors", 0),
            "lessons_loaded": m.get("lessons_loaded", 0),
            "lessons_generated": m.get("lessons_generated", 0),
            "elapsed_s": round(elapsed, 1),
        })

    show_final_summary(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
