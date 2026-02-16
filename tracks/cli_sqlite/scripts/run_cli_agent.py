#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from config import load_config
from tracks.cli_sqlite.agent_cli import (
    ARCHITECTURE_MODES,
    DEFAULT_CRITIC_MODEL,
    DEFAULT_ARCHITECTURE_MODE,
    DEFAULT_EXECUTOR_MODEL,
    DEFAULT_LEARNING_MODE,
    DEFAULT_TRANSFER_RETRIEVAL_MAX_RESULTS,
    DEFAULT_TRANSFER_RETRIEVAL_SCORE_WEIGHT,
    LEARNING_MODES,
    run_cli_agent,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--task", default="")
    ap.add_argument("--session", required=True, type=int)
    ap.add_argument("--max-steps", type=int, default=12)
    ap.add_argument("--domain", default="sqlite", choices=["sqlite", "gridtool", "fluxtool", "artic", "shell"],
                     help="Domain adapter to use (default: sqlite)")
    ap.add_argument("--learning-mode", default=DEFAULT_LEARNING_MODE, choices=LEARNING_MODES)
    ap.add_argument("--architecture-mode", default=DEFAULT_ARCHITECTURE_MODE, choices=ARCHITECTURE_MODES)
    ap.add_argument("--model-executor", default=DEFAULT_EXECUTOR_MODEL)
    ap.add_argument("--model-critic", default=DEFAULT_CRITIC_MODEL)
    ap.add_argument("--model-judge", default=None,
                     help="Model for LLM judge (default: one tier above executor)")
    ap.add_argument("--auto-escalate-critic", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--escalation-score-threshold", type=float, default=0.75)
    ap.add_argument("--escalation-consecutive-runs", type=int, default=2)
    ap.add_argument("--require-skill-read", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--posttask-mode", choices=["candidate", "direct"], default="candidate")
    ap.add_argument("--no-posttask-learn", action="store_true")
    ap.add_argument(
        "--memory-v2-demo-mode",
        action="store_true",
        help="Suppress legacy posttask_hook/promotion_gate skill patching while keeping Memory V2 active",
    )
    ap.add_argument("--opaque-tools", action="store_true", help="Use opaque tool names to test skill-reading behavior")
    ap.add_argument("--bootstrap", action="store_true",
                     help="Bootstrap mode: no skill docs, agent learns from scratch via lessons only")
    ap.add_argument("--cryptic-errors", action="store_true",
                     help="Cryptic error mode: strip helpful hints from tool error messages")
    ap.add_argument("--semi-helpful-errors", action="store_true",
                     help="Semi-helpful error mode: hint at fixes without full syntax")
    ap.add_argument("--mixed-errors", action="store_true",
                     help="Mixed mode: semi-helpful for simple commands, cryptic for core pipeline commands")
    ap.add_argument(
        "--enable-transfer-retrieval",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable cross-domain transfer lane for on-error Memory V2 retrieval",
    )
    ap.add_argument(
        "--transfer-retrieval-max-results",
        type=int,
        default=DEFAULT_TRANSFER_RETRIEVAL_MAX_RESULTS,
        help="Maximum transfer-lane hints per failed step",
    )
    ap.add_argument(
        "--transfer-retrieval-score-weight",
        type=float,
        default=DEFAULT_TRANSFER_RETRIEVAL_SCORE_WEIGHT,
        help="Score multiplier applied to transfer-lane candidates",
    )
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    result = run_cli_agent(
        cfg=cfg,
        task_id=args.task_id,
        task=args.task or None,
        session_id=args.session,
        max_steps=args.max_steps,
        domain=args.domain,
        learning_mode=args.learning_mode,
        architecture_mode=args.architecture_mode,
        model_executor=args.model_executor.strip() or DEFAULT_EXECUTOR_MODEL,
        model_critic=args.model_critic.strip() or DEFAULT_CRITIC_MODEL,
        model_judge=args.model_judge.strip() if args.model_judge else None,
        posttask_mode=args.posttask_mode,
        posttask_learn=not args.no_posttask_learn,
        memory_v2_demo_mode=bool(args.memory_v2_demo_mode),
        verbose=args.verbose,
        auto_escalate_critic=bool(args.auto_escalate_critic),
        escalation_score_threshold=args.escalation_score_threshold,
        escalation_consecutive_runs=max(1, args.escalation_consecutive_runs),
        require_skill_read=bool(args.require_skill_read) and not args.bootstrap,
        opaque_tools=bool(args.opaque_tools),
        bootstrap=bool(args.bootstrap),
        cryptic_errors=bool(args.cryptic_errors),
        semi_helpful_errors=bool(args.semi_helpful_errors),
        mixed_errors=bool(args.mixed_errors),
        enable_transfer_retrieval=bool(args.enable_transfer_retrieval),
        transfer_retrieval_max_results=max(0, int(args.transfer_retrieval_max_results)),
        transfer_retrieval_score_weight=max(0.0, float(args.transfer_retrieval_score_weight)),
    )
    print(json_dump(result.metrics))
    return 0


def json_dump(payload: object) -> str:
    import json

    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)


if __name__ == "__main__":
    raise SystemExit(main())
