#!/usr/bin/env python3
"""Gate test: prove Space key starts/stops FL Studio playback.

Two phases:
  1. Press Space → start playback → human confirms audio
  2. Press Space → stop playback → human confirms silence

Each phase is a separate agent run with its own session log.
Deterministic pass/fail: scans events.jsonl for a key action containing "space" with ok=true.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import run_agent
from config import load_config


def _verify_space_in_events(session_id: int) -> bool:
    """Return True if events.jsonl contains a successful key action with 'space'."""
    jsonl = Path("sessions") / f"session-{session_id:03d}" / "events.jsonl"
    if not jsonl.exists():
        print(f"  FAIL: {jsonl} not found")
        return False
    for line in jsonl.read_text().splitlines():
        ev = json.loads(line)
        inp = ev.get("tool_input", {})
        if ev.get("tool") == "computer" and inp.get("action") == "key":
            text = (inp.get("text") or "").lower()
            if "space" in text and ev.get("ok"):
                return True
    print(f"  FAIL: no successful key(space) event in {jsonl}")
    return False


def main() -> int:
    cfg = load_config()
    passed = 0

    # ── Phase 1: Start playback ──────────────────────────────────────
    print("\n═══ Phase 1: Start Playback ═══")
    res1 = run_agent(
        cfg=cfg,
        task=(
            "Take a screenshot of FL Studio. "
            "Then press the Space key to start playback. "
            "Then take a screenshot to verify the transport is now playing. "
            "Then stop."
        ),
        session_id=7,
        max_steps=3,
        model=cfg.model_decider,
        allowed_actions={"screenshot", "key"},
    )
    print(f"  metrics: steps={res1.metrics['steps']}  "
          f"elapsed={res1.metrics.get('elapsed_s', 0):.1f}s  "
          f"errors={res1.metrics['tool_errors']}")

    if _verify_space_in_events(7):
        print("  SPACE_SENT_START")
        passed += 1
    else:
        print("  Phase 1 FAILED — space key event not recorded")

    # Human checkpoint
    print("\n>>> CHECK: Is the FL Studio transport playing / do you hear audio?")
    answer = input(">>> Type 'y' if yes, anything else to note failure: ").strip().lower()
    human_start = answer == "y"
    print(f"  Human confirmation (start): {'YES' if human_start else 'NO'}")

    # ── Phase 2: Stop playback ───────────────────────────────────────
    print("\n═══ Phase 2: Stop Playback ═══")
    res2 = run_agent(
        cfg=cfg,
        task=(
            "Press the Space key to stop playback. "
            "Then take a screenshot to confirm the transport has stopped. "
            "Then stop."
        ),
        session_id=8,
        max_steps=3,
        model=cfg.model_decider,
        allowed_actions={"screenshot", "key"},
    )
    print(f"  metrics: steps={res2.metrics['steps']}  "
          f"elapsed={res2.metrics.get('elapsed_s', 0):.1f}s  "
          f"errors={res2.metrics['tool_errors']}")

    if _verify_space_in_events(8):
        print("  SPACE_SENT_STOP")
        passed += 1
    else:
        print("  Phase 2 FAILED — space key event not recorded")

    # Human checkpoint
    print("\n>>> CHECK: Has the transport stopped / is audio silent?")
    answer = input(">>> Type 'y' if yes, anything else to note failure: ").strip().lower()
    human_stop = answer == "y"
    print(f"  Human confirmation (stop): {'YES' if human_stop else 'NO'}")

    # ── Summary ──────────────────────────────────────────────────────
    print("\n═══ Summary ═══")
    print(f"  Automated checks passed: {passed}/2")
    print(f"  Human start confirmed:   {'PASS' if human_start else 'FAIL'}")
    print(f"  Human stop confirmed:    {'PASS' if human_stop else 'FAIL'}")
    all_pass = passed == 2 and human_start and human_stop
    print(f"  Overall: {'PASS ✓' if all_pass else 'FAIL ✗'}")
    print(f"  Sessions: sessions/session-007/, sessions/session-008/")
    print(f"  Screenshots: session-007/step-*.png, session-008/step-*.png")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
