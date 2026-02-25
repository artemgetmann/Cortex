from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUN_LEDGER_FILENAME = "run_ledger.jsonl"
RUN_LIFECYCLE_FILENAME = "run_lifecycle.jsonl"
VARIANT_SCOREBOARD_FILENAME = "variant_scoreboard.jsonl"
MAX_ERROR_SUMMARY_CHARS = 240

LIFECYCLE_EVENTS: frozenset[str] = frozenset(
    {
        "queued",
        "started",
        "step",
        "contract_gap_retry",
        "completed",
        "failed",
        "canceled",
        "timed_out",
    }
)

SELF_EDIT_GATE_EVENT_NAME = "self_edit_gate"
SELF_EDIT_GATE_STAGES: frozenset[str] = frozenset({"proposal", "patch", "promotion"})
SELF_EDIT_GATE_STATUSES: frozenset[str] = frozenset({"proposed", "accepted", "rejected"})


def build_run_id(*, session_id: int, started_at_ts: float) -> str:
    millis = int(float(started_at_ts) * 1000.0)
    return f"run-{int(session_id)}-{millis}"


def format_utc_timestamp(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_error_summary(error: Any) -> str:
    text = str(error or "").strip()
    if not text:
        return ""
    compact = " ".join(text.replace("\n", " ").replace("\r", " ").split())
    if len(compact) <= MAX_ERROR_SUMMARY_CHARS:
        return compact
    return compact[: MAX_ERROR_SUMMARY_CHARS - 3] + "..."


def run_ledger_path(*, sessions_root: Path) -> Path:
    return sessions_root / RUN_LEDGER_FILENAME


def run_lifecycle_path(*, sessions_root: Path) -> Path:
    return sessions_root / RUN_LIFECYCLE_FILENAME


def variant_scoreboard_path(*, sessions_root: Path) -> Path:
    return sessions_root / VARIANT_SCOREBOARD_FILENAME


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def append_run_ledger_entry(
    *,
    sessions_root: Path,
    run_id: str,
    session_id: int,
    task_id: str,
    domain: str,
    learn_mode: str,
    started_at: str,
    ended_at: str,
    status: str,
    error_summary: str,
) -> None:
    append_jsonl(
        run_ledger_path(sessions_root=sessions_root),
        {
            "run_id": str(run_id),
            "session_id": int(session_id),
            "task_id": str(task_id),
            "domain": str(domain),
            "learn_mode": str(learn_mode),
            "started_at": str(started_at),
            "ended_at": str(ended_at),
            "status": str(status),
            "error_summary": normalize_error_summary(error_summary),
        },
    )


def append_lifecycle_event(
    *,
    sessions_root: Path,
    run_id: str,
    session_id: int,
    task_id: str,
    domain: str,
    learn_mode: str,
    event: str,
    step: int | None = None,
    trigger: str | None = None,
) -> None:
    event_name = str(event).strip().lower()
    if event_name not in LIFECYCLE_EVENTS:
        return
    row: dict[str, Any] = {
        "ts": time.time(),
        "run_id": str(run_id),
        "session_id": int(session_id),
        "task_id": str(task_id),
        "domain": str(domain),
        "learn_mode": str(learn_mode),
        "event": event_name,
    }
    if step is not None:
        row["step"] = int(step)
    if trigger:
        row["trigger"] = str(trigger)
    append_jsonl(run_lifecycle_path(sessions_root=sessions_root), row)


def append_self_edit_gate_event(
    *,
    sessions_root: Path,
    run_id: str,
    session_id: int,
    task_id: str,
    domain: str,
    learn_mode: str,
    stage: str,
    status: str,
    reason: str | None = None,
    rollback_reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    stage_name = str(stage).strip().lower()
    status_name = str(status).strip().lower()
    if stage_name not in SELF_EDIT_GATE_STAGES:
        return
    if status_name not in SELF_EDIT_GATE_STATUSES:
        return
    row: dict[str, Any] = {
        "ts": time.time(),
        "run_id": str(run_id),
        "session_id": int(session_id),
        "task_id": str(task_id),
        "domain": str(domain),
        "learn_mode": str(learn_mode),
        "event": SELF_EDIT_GATE_EVENT_NAME,
        "stage": stage_name,
        "status": status_name,
    }
    if reason:
        row["reason"] = str(reason)
    if rollback_reason:
        row["rollback_reason"] = str(rollback_reason)
    if isinstance(metadata, dict) and metadata:
        row["metadata"] = dict(metadata)
    append_jsonl(run_lifecycle_path(sessions_root=sessions_root), row)


def read_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows
