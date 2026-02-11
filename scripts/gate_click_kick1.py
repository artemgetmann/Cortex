#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import run_agent
from config import load_config


def main() -> int:
    cfg = load_config()
    task = (
        "In FL Studio: ensure Channel Rack is open (F6). "
        "Toggle the 1st step button in the '808 Kick' row (the very first step square). "
        "Use Hint Bar verification before clicking. Then stop."
    )
    # Use Opus for dense UI click tasks; it supports computer_20251124 (zoom).
    res = run_agent(cfg=cfg, task=task, session_id=5, max_steps=18, model=cfg.model_heavy)
    print('metrics:', res.metrics)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
