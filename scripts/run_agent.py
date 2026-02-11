#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import run_agent
from config import load_config


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--session", type=int, default=1)
    ap.add_argument("--max-steps", type=int, default=80)
    ap.add_argument("--model", default="")
    ap.add_argument("--no-skills", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    model = args.model.strip() or cfg.model_heavy
    res = run_agent(
        cfg=cfg,
        task=args.task,
        session_id=args.session,
        max_steps=args.max_steps,
        model=model,
        load_skills=not args.no_skills,
    )
    print("metrics:", res.metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
