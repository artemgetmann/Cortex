from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SessionPaths:
    session_dir: Path
    jsonl_path: Path
    metrics_path: Path


def ensure_session(session_id: int, *, reset_existing: bool = True) -> SessionPaths:
    session_dir = Path("sessions") / f"session-{session_id:03d}"
    session_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = session_dir / "events.jsonl"
    metrics_path = session_dir / "metrics.json"
    if reset_existing:
        if jsonl_path.exists():
            jsonl_path.unlink()
        if metrics_path.exists():
            metrics_path.unlink()
        for shot in session_dir.glob("step-*.png"):
            try:
                shot.unlink()
            except OSError:
                # Keep run startup resilient if a screenshot is temporarily locked.
                pass

    return SessionPaths(session_dir=session_dir, jsonl_path=jsonl_path, metrics_path=metrics_path)


def write_event(jsonl_path: Path, event: dict[str, Any]) -> None:
    event = dict(event)
    event.setdefault("ts", time.time())
    with jsonl_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=True) + "\n")


def write_metrics(metrics_path: Path, metrics: dict[str, Any]) -> None:
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")
