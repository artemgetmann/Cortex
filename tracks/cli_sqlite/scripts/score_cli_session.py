#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tracks.cli_sqlite.eval_cli import evaluate_cli_session
from tracks.cli_sqlite.memory_cli import read_events

TRACK_ROOT = Path(__file__).resolve().parents[1]
SESSIONS_ROOT = TRACK_ROOT / "sessions"
TASKS_ROOT = TRACK_ROOT / "tasks"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True, type=int)
    ap.add_argument("--task-id", required=True)
    args = ap.parse_args()

    session_dir = SESSIONS_ROOT / f"session-{args.session:03d}"
    events_path = session_dir / "events.jsonl"
    db_path = session_dir / "task.db"
    metrics_path = session_dir / "metrics.json"

    if not events_path.exists():
        raise SystemExit(f"Missing events file: {events_path}")
    if not db_path.exists():
        raise SystemExit(f"Missing sqlite db file: {db_path}")

    task = f"SQLite task id: {args.task_id}"
    if metrics_path.exists():
        try:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            if isinstance(metrics, dict):
                raw_task = metrics.get("task")
                if isinstance(raw_task, str) and raw_task.strip():
                    task = raw_task
        except Exception:
            pass

    result = evaluate_cli_session(
        task=task,
        task_id=args.task_id,
        events=read_events(events_path),
        db_path=db_path,
        tasks_root=TASKS_ROOT,
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
