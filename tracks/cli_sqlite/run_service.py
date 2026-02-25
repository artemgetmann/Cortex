from __future__ import annotations

import contextlib
import fcntl
import json
import os
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


TRACK_ROOT = Path(__file__).resolve().parent
DEFAULT_STATE_PATH = TRACK_ROOT / "sessions" / "run_service_state.json"
DEFAULT_LIFECYCLE_PATH = TRACK_ROOT / "sessions" / "run_lifecycle.jsonl"
ENV_STATE_PATH = "CORTEX_RUN_SERVICE_STATE_PATH"
ENV_LIFECYCLE_PATH = "CORTEX_RUN_SERVICE_LIFECYCLE_PATH"

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_CANCEL_REQUESTED = "cancel_requested"
STATUS_CANCELLED = "cancelled"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

ACTIVE_STATUSES = {STATUS_PENDING, STATUS_RUNNING, STATUS_CANCEL_REQUESTED}
TERMINAL_STATUSES = {STATUS_CANCELLED, STATUS_COMPLETED, STATUS_FAILED}
ALL_STATUSES = ACTIVE_STATUSES | TERMINAL_STATUSES

_STATE_VERSION = 1


class RunServiceError(RuntimeError):
    """Raised when run-service state is invalid or an update is impossible."""


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    session_id: int
    task_id: str
    domain: str
    status: str
    created_at_epoch_s: float
    updated_at_epoch_s: float
    started_at_epoch_s: float | None = None
    finished_at_epoch_s: float | None = None
    cancel_requested: bool = False
    cancel_reason: str | None = None
    error: str | None = None
    last_step: int | None = None
    metadata: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    followups: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "domain": self.domain,
            "status": self.status,
            "created_at_epoch_s": self.created_at_epoch_s,
            "updated_at_epoch_s": self.updated_at_epoch_s,
            "started_at_epoch_s": self.started_at_epoch_s,
            "finished_at_epoch_s": self.finished_at_epoch_s,
            "cancel_requested": self.cancel_requested,
            "cancel_reason": self.cancel_reason,
            "error": self.error,
            "last_step": self.last_step,
            "metadata": self.metadata or {},
            "result": self.result or {},
            "followups": [dict(item) for item in (self.followups or [])],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RunRecord":
        status = str(payload.get("status", STATUS_PENDING)).strip().lower()
        if status not in ALL_STATUSES:
            raise RunServiceError(f"Unknown run status: {status!r}")
        return cls(
            run_id=str(payload.get("run_id", "")).strip(),
            session_id=int(payload.get("session_id", 0) or 0),
            task_id=str(payload.get("task_id", "")).strip(),
            domain=str(payload.get("domain", "")).strip(),
            status=status,
            created_at_epoch_s=float(payload.get("created_at_epoch_s", 0.0) or 0.0),
            updated_at_epoch_s=float(payload.get("updated_at_epoch_s", 0.0) or 0.0),
            started_at_epoch_s=(
                float(payload.get("started_at_epoch_s"))
                if payload.get("started_at_epoch_s") is not None
                else None
            ),
            finished_at_epoch_s=(
                float(payload.get("finished_at_epoch_s"))
                if payload.get("finished_at_epoch_s") is not None
                else None
            ),
            cancel_requested=bool(payload.get("cancel_requested", False)),
            cancel_reason=(
                str(payload.get("cancel_reason", "")).strip()
                if payload.get("cancel_reason") is not None
                else None
            ),
            error=(
                str(payload.get("error", "")).strip()
                if payload.get("error") is not None
                else None
            ),
            last_step=(
                int(payload.get("last_step"))
                if payload.get("last_step") is not None
                else None
            ),
            metadata=dict(payload.get("metadata") or {}),
            result=dict(payload.get("result") or {}),
            followups=_normalize_followups(payload.get("followups")),
        )


def _normalize_followups(payload: Any) -> list[dict[str, Any]]:
    rows = payload if isinstance(payload, list) else []
    parsed: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text", "")).strip()
        source = str(row.get("source", "")).strip()
        ts_raw = row.get("ts")
        try:
            ts = float(ts_raw)
        except (TypeError, ValueError):
            continue
        if not text or not source:
            continue
        parsed.append({"text": text, "source": source, "ts": ts})
    return parsed


@contextlib.contextmanager
def _locked_state_file(path: Path, *, mutate: bool) -> Iterator[tuple[Any, dict[str, Any]]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        # Cross-process lock so transports and runners can safely update/read
        # the same state file even when invoked in different processes.
        lock_kind = fcntl.LOCK_EX if mutate else fcntl.LOCK_SH
        fcntl.flock(handle.fileno(), lock_kind)
        handle.seek(0)
        raw = handle.read().strip()
        state = _parse_state(raw)
        try:
            yield handle, state
        finally:
            if mutate:
                handle.seek(0)
                handle.truncate()
                handle.write(json.dumps(state, ensure_ascii=True, indent=2) + "\n")
                handle.flush()
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _parse_state(raw: str) -> dict[str, Any]:
    if not raw:
        return {"version": _STATE_VERSION, "next_sequence": 1, "runs": {}, "next_session_id": 1000}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RunServiceError(f"Run-service state is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RunServiceError("Run-service state payload must be an object.")
    payload.setdefault("version", _STATE_VERSION)
    payload.setdefault("next_sequence", 1)
    payload.setdefault("next_session_id", 1000)
    payload.setdefault("runs", {})
    runs = payload.get("runs")
    if not isinstance(runs, dict):
        raise RunServiceError("Run-service state field 'runs' must be an object.")
    return payload


def _format_run_id(*, sequence: int, now_epoch_s: float) -> str:
    epoch_ms = int(now_epoch_s * 1000)
    # Stable, sortable identifier: timestamp + monotonic sequence.
    return f"run_{epoch_ms:013d}_{sequence:08d}"


def _normalize_state_path(state_path: Path | None) -> Path:
    if state_path is not None:
        return state_path.resolve()
    env_path = str(os.getenv(ENV_STATE_PATH, "")).strip()
    if env_path:
        return Path(env_path).expanduser().resolve()
    return DEFAULT_STATE_PATH.resolve()


def _normalize_lifecycle_path(lifecycle_path: Path | None) -> Path:
    if lifecycle_path is not None:
        return lifecycle_path.resolve()
    env_path = str(os.getenv(ENV_LIFECYCLE_PATH, "")).strip()
    if env_path:
        return Path(env_path).expanduser().resolve()
    return DEFAULT_LIFECYCLE_PATH.resolve()


def resolve_state_path(state_path: Path | None = None) -> Path:
    return _normalize_state_path(state_path)


def resolve_lifecycle_path(lifecycle_path: Path | None = None) -> Path:
    return _normalize_lifecycle_path(lifecycle_path)


def _coerce_ts(ts: Any) -> float | None:
    try:
        return float(ts)
    except (TypeError, ValueError):
        return None


def _transition_allowed(current: str, next_status: str) -> bool:
    if current == next_status:
        return True
    if current == STATUS_PENDING:
        return next_status in {STATUS_RUNNING, STATUS_CANCEL_REQUESTED, STATUS_CANCELLED, STATUS_FAILED}
    if current == STATUS_RUNNING:
        return next_status in {STATUS_CANCEL_REQUESTED, STATUS_CANCELLED, STATUS_COMPLETED, STATUS_FAILED}
    if current == STATUS_CANCEL_REQUESTED:
        return next_status in {STATUS_CANCELLED, STATUS_COMPLETED, STATUS_FAILED}
    return False


def _read_record(state: dict[str, Any], run_id: str) -> dict[str, Any] | None:
    rows = state.get("runs", {})
    value = rows.get(run_id)
    if value is None or not isinstance(value, dict):
        return None
    return dict(value)


def generate_run_id(*, state_path: Path | None = None) -> str:
    path = _normalize_state_path(state_path)
    now = time.time()
    with _locked_state_file(path, mutate=True) as (_, state):
        sequence = int(state.get("next_sequence", 1) or 1)
        state["next_sequence"] = sequence + 1
        return _format_run_id(sequence=sequence, now_epoch_s=now)


def allocate_session_id(*, state_path: Path | None = None) -> int:
    path = _normalize_state_path(state_path)
    with _locked_state_file(path, mutate=True) as (_, state):
        next_session = int(state.get("next_session_id", 1000) or 1000)
        state["next_session_id"] = next_session + 1
        return next_session


def start_run(
    *,
    task_id: str,
    domain: str,
    session_id: int,
    metadata: dict[str, Any] | None = None,
    run_id: str | None = None,
    state_path: Path | None = None,
) -> RunRecord:
    path = _normalize_state_path(state_path)
    now = time.time()
    with _locked_state_file(path, mutate=True) as (_, state):
        runs = state["runs"]
        if run_id:
            rid = str(run_id).strip()
            if not rid:
                raise RunServiceError("run_id cannot be empty.")
            if rid in runs:
                raise RunServiceError(f"run_id already exists: {rid}")
        else:
            sequence = int(state.get("next_sequence", 1) or 1)
            state["next_sequence"] = sequence + 1
            rid = _format_run_id(sequence=sequence, now_epoch_s=now)

        record = RunRecord(
            run_id=rid,
            session_id=max(0, int(session_id)),
            task_id=str(task_id).strip(),
            domain=str(domain).strip(),
            status=STATUS_RUNNING,
            created_at_epoch_s=now,
            updated_at_epoch_s=now,
            started_at_epoch_s=now,
            metadata=dict(metadata or {}),
        )
        runs[rid] = record.to_dict()
        return record


def get_run(run_id: str, *, state_path: Path | None = None) -> RunRecord | None:
    rid = str(run_id).strip()
    if not rid:
        return None
    path = _normalize_state_path(state_path)
    with _locked_state_file(path, mutate=False) as (_, state):
        row = _read_record(state, rid)
    return RunRecord.from_dict(row) if row else None


def list_active(*, state_path: Path | None = None) -> list[RunRecord]:
    path = _normalize_state_path(state_path)
    with _locked_state_file(path, mutate=False) as (_, state):
        rows: list[RunRecord] = []
        for payload in state.get("runs", {}).values():
            if not isinstance(payload, dict):
                continue
            record = RunRecord.from_dict(payload)
            if record.status in ACTIVE_STATUSES:
                rows.append(record)
    rows.sort(key=lambda item: item.updated_at_epoch_s, reverse=True)
    return rows


def update_run(
    run_id: str,
    *,
    status: str | None = None,
    cancel_requested: bool | None = None,
    cancel_reason: str | None = None,
    error: str | None = None,
    last_step: int | None = None,
    result: dict[str, Any] | None = None,
    state_path: Path | None = None,
) -> RunRecord | None:
    rid = str(run_id).strip()
    if not rid:
        return None
    path = _normalize_state_path(state_path)
    now = time.time()
    with _locked_state_file(path, mutate=True) as (_, state):
        row = _read_record(state, rid)
        if row is None:
            return None
        current = RunRecord.from_dict(row)
        next_status = current.status if status is None else str(status).strip().lower()
        if next_status not in ALL_STATUSES:
            raise RunServiceError(f"Unknown status transition target: {next_status!r}")
        if not _transition_allowed(current.status, next_status):
            raise RunServiceError(f"Invalid status transition: {current.status!r} -> {next_status!r}")

        merged = current.to_dict()
        merged["status"] = next_status
        merged["updated_at_epoch_s"] = now
        merged["cancel_requested"] = (
            bool(cancel_requested)
            if cancel_requested is not None
            else bool(current.cancel_requested or next_status in {STATUS_CANCEL_REQUESTED, STATUS_CANCELLED})
        )
        if cancel_reason is not None:
            merged["cancel_reason"] = str(cancel_reason).strip() or None
        if error is not None:
            merged["error"] = str(error).strip() or None
        if last_step is not None:
            merged["last_step"] = int(last_step)
        if result is not None:
            merged["result"] = dict(result)
        if next_status in TERMINAL_STATUSES and merged.get("finished_at_epoch_s") is None:
            merged["finished_at_epoch_s"] = now
        if next_status == STATUS_RUNNING and merged.get("started_at_epoch_s") is None:
            merged["started_at_epoch_s"] = now
        state["runs"][rid] = merged
        return RunRecord.from_dict(merged)


def cancel_run(
    run_id: str,
    *,
    reason: str | None = None,
    state_path: Path | None = None,
) -> RunRecord | None:
    current = get_run(run_id, state_path=state_path)
    if current is None:
        return None
    if current.status in TERMINAL_STATUSES:
        return current
    return update_run(
        run_id,
        status=STATUS_CANCEL_REQUESTED,
        cancel_requested=True,
        cancel_reason=str(reason).strip() if reason else None,
        state_path=state_path,
    )


def mark_heartbeat(
    run_id: str,
    *,
    last_step: int | None = None,
    state_path: Path | None = None,
) -> RunRecord | None:
    return update_run(run_id, last_step=last_step, state_path=state_path)


def is_cancel_requested(run_id: str, *, state_path: Path | None = None) -> bool:
    row = get_run(run_id, state_path=state_path)
    if row is None:
        return False
    return bool(row.cancel_requested or row.status in {STATUS_CANCEL_REQUESTED, STATUS_CANCELLED})


def append_followup(
    run_id: str,
    text: str,
    source: str,
    ts: float,
    *,
    state_path: Path | None = None,
) -> RunRecord | None:
    rid = str(run_id).strip()
    if not rid:
        return None
    followup_text = str(text).strip()
    if not followup_text:
        raise RunServiceError("Follow-up text cannot be empty.")
    followup_source = str(source).strip()
    if not followup_source:
        raise RunServiceError("Follow-up source cannot be empty.")
    followup_ts = _coerce_ts(ts)
    if followup_ts is None:
        raise RunServiceError("Follow-up timestamp must be numeric.")

    path = _normalize_state_path(state_path)
    now = time.time()
    with _locked_state_file(path, mutate=True) as (_, state):
        row = _read_record(state, rid)
        if row is None:
            return None
        current = RunRecord.from_dict(row)
        merged = current.to_dict()
        followups = _normalize_followups(merged.get("followups"))
        followups.append({"text": followup_text, "source": followup_source, "ts": followup_ts})
        merged["followups"] = followups
        merged["updated_at_epoch_s"] = now
        state["runs"][rid] = merged
        return RunRecord.from_dict(merged)


def list_events(
    run_id: str,
    *,
    from_ts: float | None = None,
    max_events: int = 200,
    lifecycle_path: Path | None = None,
) -> list[dict[str, Any]]:
    rid = str(run_id).strip()
    if not rid:
        return []
    cursor = _coerce_ts(from_ts) if from_ts is not None else None
    limit = max(0, int(max_events))
    if limit == 0:
        return []

    path = _normalize_lifecycle_path(lifecycle_path)
    if not path.exists():
        return []
    if cursor is None:
        # For dashboard/status calls we only need the newest tail. Keep this
        # bounded so large lifecycle logs do not force unbounded memory usage.
        tail: deque[dict[str, Any]] = deque(maxlen=limit)
    else:
        # Cursor mode is used by incremental polling; return earliest unseen
        # events first so clients can advance deterministically.
        rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict):
                continue
            if str(parsed.get("run_id", "")).strip() != rid:
                continue
            ts = _coerce_ts(parsed.get("ts"))
            if ts is None:
                continue
            # Cursor is exclusive so clients can pass the last seen ts.
            if cursor is not None and ts <= cursor:
                continue
            row = dict(parsed)
            if cursor is None:
                tail.append(row)
            else:
                rows.append(row)
                if len(rows) >= limit:
                    break

    if cursor is None:
        return list(tail)
    return rows


def stream_run(
    run_id: str,
    *,
    from_ts: float | None = None,
    max_events: int = 200,
    state_path: Path | None = None,
    lifecycle_path: Path | None = None,
) -> dict[str, Any]:
    return {
        "run": get_run(run_id, state_path=state_path),
        "events": list_events(
            run_id,
            from_ts=from_ts,
            max_events=max_events,
            lifecycle_path=lifecycle_path,
        ),
    }
