#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import run_agent
from config import load_config

def main() -> int:
    cfg = load_config()
    res = run_agent(
        cfg=cfg,
        task="Take a screenshot of FL Studio and describe what you see. Identify whether Channel Rack is visible and where the Hint Bar is. Then stop.",
        session_id=0,
        max_steps=6,
        model=cfg.model_decider,
        allowed_actions={"screenshot"},
    )
    # Print only the final assistant text for quick sanity checking.
    last_assistant = next((m for m in reversed(res.messages) if m.get("role") == "assistant"), None)
    if last_assistant:
        print(last_assistant.get("content"))
    print("metrics:", res.metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
