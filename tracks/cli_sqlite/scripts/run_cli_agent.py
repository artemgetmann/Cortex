#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from config import load_config
from tracks.cli_sqlite.agent_cli import (
    DEFAULT_CRITIC_MODEL,
    DEFAULT_EXECUTOR_MODEL,
    run_cli_agent,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--task", default="")
    ap.add_argument("--session", required=True, type=int)
    ap.add_argument("--max-steps", type=int, default=12)
    ap.add_argument("--model-executor", default=DEFAULT_EXECUTOR_MODEL)
    ap.add_argument("--model-critic", default=DEFAULT_CRITIC_MODEL)
    ap.add_argument("--auto-escalate-critic", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--escalation-score-threshold", type=float, default=0.75)
    ap.add_argument("--escalation-consecutive-runs", type=int, default=2)
    ap.add_argument("--require-skill-read", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--posttask-mode", choices=["candidate", "direct"], default="candidate")
    ap.add_argument("--no-posttask-learn", action="store_true")
    ap.add_argument("--opaque-tools", action="store_true", help="Use opaque tool names to test skill-reading behavior")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    result = run_cli_agent(
        cfg=cfg,
        task_id=args.task_id,
        task=args.task or None,
        session_id=args.session,
        max_steps=args.max_steps,
        model_executor=args.model_executor.strip() or DEFAULT_EXECUTOR_MODEL,
        model_critic=args.model_critic.strip() or DEFAULT_CRITIC_MODEL,
        posttask_mode=args.posttask_mode,
        posttask_learn=not args.no_posttask_learn,
        verbose=args.verbose,
        auto_escalate_critic=bool(args.auto_escalate_critic),
        escalation_score_threshold=args.escalation_score_threshold,
        escalation_consecutive_runs=max(1, args.escalation_consecutive_runs),
        require_skill_read=bool(args.require_skill_read),
        opaque_tools=bool(args.opaque_tools),
    )
    print(json_dump(result.metrics))
    return 0


def json_dump(payload: object) -> str:
    import json

    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)


if __name__ == "__main__":
    raise SystemExit(main())
