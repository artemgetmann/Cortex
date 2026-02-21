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
    DEFAULT_CONTRACT_GAP_RETRY,
    DEFAULT_CONTRACT_GAP_RETRY_STEPS,
    DEFAULT_DOC_BUDGET_TOKENS,
    DEFAULT_DOC_MODE,
    DEFAULT_DOC_RETRIEVAL_MODE,
    DEFAULT_EXECUTOR_MODEL,
    DEFAULT_LEARNING_MODE,
    DEFAULT_STRUCTURED_LESSONS_REQUIRED,
    LEARNING_MODES,
    run_cli_agent,
)

BENCHMARK_DEFAULT_LEARNING_MODE = "strict" if "strict" in LEARNING_MODES else DEFAULT_LEARNING_MODE


def main() -> int:
    ap = argparse.ArgumentParser(description="Run N sessions and plot the learning curve")
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--domain", default="gridtool", choices=["sqlite", "gridtool", "fluxtool", "artic", "shell"])
    ap.add_argument("--learning-mode", default=BENCHMARK_DEFAULT_LEARNING_MODE, choices=LEARNING_MODES)
    ap.add_argument("--sessions", type=int, default=5, help="Number of sequential sessions")
    ap.add_argument("--start-session", type=int, default=9001, help="Starting session ID")
    ap.add_argument("--max-steps", type=int, default=12)
    ap.add_argument("--bootstrap", action="store_true", help="No skill docs, lessons only")
    ap.add_argument("--cryptic-errors", action="store_true", help="Cryptic errors: strip hints from error messages")
    ap.add_argument("--semi-helpful-errors", action="store_true", help="Semi-helpful errors: hint at fixes without full syntax")
    ap.add_argument("--mixed-errors", action="store_true", help="Mixed mode: semi-helpful for simple commands, cryptic for core pipeline commands")
    ap.add_argument("--model-executor", default=DEFAULT_EXECUTOR_MODEL)
    ap.add_argument("--model-judge", default=DEFAULT_EXECUTOR_MODEL)
    ap.add_argument("--llm-backend", default="anthropic", choices=["anthropic", "claude_print"])
    ap.add_argument("--posttask-mode", choices=["candidate", "direct"], default="direct")
    ap.add_argument("--no-posttask-learn", action="store_true")
    ap.add_argument("--documentation", action="append", default=[])
    ap.add_argument("--doc-mode", default=DEFAULT_DOC_MODE, choices=["none", "lossy", "full"])
    ap.add_argument("--doc-budget-tokens", type=int, default=DEFAULT_DOC_BUDGET_TOKENS)
    ap.add_argument("--doc-retrieval", default=DEFAULT_DOC_RETRIEVAL_MODE, choices=["off", "auto"])
    ap.add_argument("--doc-retriever-model", default="")
    ap.add_argument("--judge-docs", default="off", choices=["on", "off"])
    ap.add_argument("--executor-docs", default="off", choices=["on", "off"])
    ap.add_argument(
        "--judge-diagnostic",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Run LLM judge even when contract passes for per-run diagnostics.",
    )
    ap.add_argument(
        "--contract-gap-retry",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_CONTRACT_GAP_RETRY,
        help="Enable deterministic pre-stop contract gap checker with one retry.",
    )
    ap.add_argument(
        "--contract-gap-retry-steps",
        type=int,
        default=DEFAULT_CONTRACT_GAP_RETRY_STEPS,
        help="Retry budget for contract gap checker (hard-capped to 1 in runtime).",
    )
    ap.add_argument(
        "--structured-lessons-required",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_STRUCTURED_LESSONS_REQUIRED,
        help="Require V2 candidates to include reason_code + gap_type metadata.",
    )
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    results: list[dict] = []

    # Clear escalation state for clean experiment
    escalation_path = Path(__file__).resolve().parents[1] / "learning" / "critic_escalation_state.json"
    if escalation_path.exists():
        escalation_path.unlink()

    print(f"\n{'='*60}")
    print(f"  Learning Curve Experiment")
    print(f"  task={args.task_id}  domain={args.domain}  learning_mode={args.learning_mode}  bootstrap={args.bootstrap}")
    print(
        f"  cryptic_errors={args.cryptic_errors}  semi_helpful={args.semi_helpful_errors}  mixed_errors={args.mixed_errors}  "
        f"sessions={args.sessions}  executor_model={args.model_executor} judge_model={args.model_judge} "
        f"backend={args.llm_backend} critic=executor(locked)"
    )
    print(
        f"  docs mode={args.doc_mode} retrieval={args.doc_retrieval} "
        f"executor_docs={args.executor_docs} judge_docs={args.judge_docs} "
        f"posttask_learn={not bool(args.no_posttask_learn)}"
    )
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
            learning_mode=args.learning_mode,
            model_executor=args.model_executor.strip() or DEFAULT_EXECUTOR_MODEL,
            model_critic=args.model_executor.strip() or DEFAULT_EXECUTOR_MODEL,
            model_judge=args.model_judge.strip() if args.model_judge else (args.model_executor.strip() or DEFAULT_EXECUTOR_MODEL),
            posttask_mode=args.posttask_mode,
            posttask_learn=not bool(args.no_posttask_learn),
            verbose=args.verbose,
            auto_escalate_critic=False,
            escalation_score_threshold=0.75,
            escalation_consecutive_runs=2,
            require_skill_read=not args.bootstrap,
            opaque_tools=False,
            bootstrap=args.bootstrap,
            cryptic_errors=args.cryptic_errors,
            semi_helpful_errors=args.semi_helpful_errors,
            mixed_errors=args.mixed_errors,
            documentation=[str(item).strip() for item in args.documentation if str(item).strip()],
            doc_mode=args.doc_mode,
            doc_budget_tokens=max(128, int(args.doc_budget_tokens)),
            doc_retrieval=args.doc_retrieval,
            doc_retriever_model=str(args.doc_retriever_model).strip() or None,
            judge_docs=args.judge_docs == "on",
            executor_docs=args.executor_docs == "on",
            judge_diagnostic=bool(args.judge_diagnostic),
            contract_gap_retry=bool(args.contract_gap_retry),
            contract_gap_retry_steps=max(0, int(args.contract_gap_retry_steps)),
            structured_lessons_required=bool(args.structured_lessons_required),
            llm_backend=args.llm_backend,
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
