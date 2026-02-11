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
        "Use zoom to see the step buttons clearly. "
        "If the Hint Bar isn't readable/visible, proceed anyway: click the center of the first step square. "
        "After clicking, take a screenshot (or zoom) to confirm the first step changed color. Then stop."
    )
    res = run_agent(
        cfg=cfg,
        task=task,
        session_id=6,
        max_steps=16,
        model=cfg.model_heavy,
        allowed_actions={"screenshot", "zoom", "mouse_move", "left_click", "key", "wait"},
    )
    print("metrics:", res.metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

