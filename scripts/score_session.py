#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from run_eval import evaluate_drum_run


DEFAULT_TASK = "Create a 4-on-the-floor kick drum pattern in FL Studio"


def _load_events(session_id: int) -> list[dict]:
    p = Path(f"sessions/session-{session_id:04d}/events.jsonl")
    if not p.exists():
        raise FileNotFoundError(f"session file not found: {p}")
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, required=True, help="session id (e.g. 9802)")
    ap.add_argument("--task", default=DEFAULT_TASK, help="task string used for evaluator applicability")
    args = ap.parse_args()

    events = _load_events(args.session)
    out = evaluate_drum_run(args.task, events).to_dict()
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
