from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SessionPaths:
    session_dir: Path
    events_path: Path
    metrics_path: Path
    db_path: Path


def ensure_session(
    session_id: int,
    *,
    sessions_root: Path,
    reset_existing: bool = True,
) -> SessionPaths:
    session_dir = sessions_root / f"session-{session_id:03d}"
    session_dir.mkdir(parents=True, exist_ok=True)

    events_path = session_dir / "events.jsonl"
    metrics_path = session_dir / "metrics.json"
    db_path = session_dir / "task.db"

    if reset_existing:
        # Session IDs are expected to be reusable during rapid iteration.
        # Clearing all previous artifacts avoids cross-run contamination.
        for child in session_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                try:
                    child.unlink()
                except OSError:
                    pass

    return SessionPaths(
        session_dir=session_dir,
        events_path=events_path,
        metrics_path=metrics_path,
        db_path=db_path,
    )


def write_event(events_path: Path, event: dict[str, Any]) -> None:
    row = dict(event)
    row.setdefault("ts", time.time())
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=True) + "\n")


def read_events(events_path: Path) -> list[dict[str, Any]]:
    if not events_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def write_metrics(metrics_path: Path, metrics: dict[str, Any]) -> None:
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
