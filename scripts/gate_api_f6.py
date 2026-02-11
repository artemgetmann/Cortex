#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import run_agent
from config import load_config


def main() -> int:
    cfg = load_config()
    task = "Ensure FL Studio is focused. Open Channel Rack using the keyboard shortcut (F6). Then stop."
    # Keep this extremely short to reduce chances of the model "getting creative".
    res = run_agent(
        cfg=cfg,
        task=task,
        session_id=2,
        max_steps=3,
        model=cfg.model_decider,
        allowed_actions={"screenshot", "mouse_move", "left_click", "key", "wait"},
    )
    print("metrics:", res.metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
