#!/usr/bin/env python3
"""Summarize run health from run_ledger.jsonl and per-session metrics."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tracks.cli_sqlite.run_observability import read_jsonl_rows, run_ledger_path


TRACK_ROOT = Path(__file__).resolve().parents[1]
SESSIONS_ROOT = TRACK_ROOT / "sessions"


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
    return None


def _metrics_optional_float(metrics: dict[str, Any], key: str) -> float | None:
    if key not in metrics:
        return None
    try:
        return float(metrics.get(key))
    except (TypeError, ValueError):
        return None


def _metrics_optional_int(metrics: dict[str, Any], key: str) -> int | None:
    if key not in metrics:
        return None
    try:
        return int(metrics.get(key))
    except (TypeError, ValueError):
        return None


def _parse_utc_iso(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _row_success(row: dict[str, Any]) -> bool:
    eval_passed = row.get("eval_passed")
    if isinstance(eval_passed, bool):
        return eval_passed
    # Fallback for historical rows where eval metrics were not persisted.
    return str(row.get("status", "")).strip().lower() == "completed"


def _row_has_gap_signal(row: dict[str, Any]) -> bool:
    unresolved_prestop = _as_int(row.get("contract_gap_unresolved_count_prestop"), 0)
    unresolved_final = _as_int(row.get("contract_gap_unresolved_count_final"), 0)
    retry_triggered = _as_int(row.get("contract_gap_retry_triggered"), 0)
    retry_attempts = _as_int(row.get("contract_gap_retry_attempts"), 0)
    return unresolved_prestop > 0 or unresolved_final > 0 or retry_triggered > 0 or retry_attempts > 0


def _row_gap_resolved(row: dict[str, Any]) -> bool:
    if not _row_has_gap_signal(row):
        return False
    # Resolution proxy: a run had a contract-gap signal and ended with no unresolved gaps.
    return _as_int(row.get("contract_gap_unresolved_count_final"), 0) == 0


def load_recent_runs(*, sessions_root: Path, last_n: int) -> list[dict[str, Any]]:
    ledger_rows = read_jsonl_rows(run_ledger_path(sessions_root=sessions_root))
    if last_n > 0:
        ledger_rows = ledger_rows[-last_n:]
    rows: list[dict[str, Any]] = []
    for row in ledger_rows:
        if not isinstance(row, dict):
            continue
        session_id = _as_int(row.get("session_id"), -1)
        metrics_path = sessions_root / f"session-{session_id:03d}" / "metrics.json"
        metrics: dict[str, Any] = {}
        if metrics_path.exists():
            try:
                loaded = json.loads(metrics_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    metrics = loaded
            except Exception:
                metrics = {}

        started_ts = _parse_utc_iso(row.get("started_at"))
        ended_ts = _parse_utc_iso(row.get("ended_at"))
        run_duration_s = None
        if started_ts is not None and ended_ts is not None and ended_ts >= started_ts:
            run_duration_s = ended_ts - started_ts

        rows.append(
            {
                "run_id": str(row.get("run_id", "")),
                "session_id": session_id,
                "task_id": str(row.get("task_id", "")),
                "domain": str(row.get("domain", "")),
                "learn_mode": str(row.get("learn_mode", "")),
                "started_at": str(row.get("started_at", "")),
                "ended_at": str(row.get("ended_at", "")),
                "status": str(row.get("status", "")).strip().lower(),
                "error_summary": str(row.get("error_summary", "")),
                "lesson_writes": _as_int(metrics.get("v2_lessons_generated"), 0),
                "retrieval_help_ratio": _as_float(metrics.get("v2_retrieval_help_ratio"), 0.0),
                "eval_passed": _as_optional_bool(metrics.get("eval_passed")),
                "fingerprint_recurrence_before": _metrics_optional_float(metrics, "v2_fingerprint_recurrence_before"),
                "fingerprint_recurrence_after": _metrics_optional_float(metrics, "v2_fingerprint_recurrence_after"),
                "contract_gap_unresolved_count_prestop": _metrics_optional_int(
                    metrics, "contract_gap_unresolved_count_prestop"
                ),
                "contract_gap_unresolved_count_final": _metrics_optional_int(
                    metrics, "contract_gap_unresolved_count_final"
                ),
                "contract_gap_retry_triggered": _metrics_optional_int(metrics, "contract_gap_retry_triggered"),
                "contract_gap_retry_attempts": _metrics_optional_int(metrics, "contract_gap_retry_attempts"),
                "transfer_lane_activations": _as_int(metrics.get("v2_transfer_lane_activations"), 0),
                "transfer_retrieval_enabled": bool(metrics.get("v2_transfer_retrieval_enabled", False)),
                "started_ts": started_ts,
                "ended_ts": ended_ts,
                "run_duration_s": run_duration_s,
            }
        )
    return rows


def summarize_run_health(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    if total == 0:
        return {
            "runs": 0,
            "fail_rate": 0.0,
            "cancel_rate": 0.0,
            "timeout_rate": 0.0,
            "lesson_writes_total": 0,
            "lesson_write_runs": 0,
            "retrieval_help_ratio_mean": None,
            "retrieval_help_trend_delta": None,
            "first_success_session": None,
            "first_success_run_index": None,
            "repeated_fingerprint_decay_proxy_mean": None,
            "repeated_fingerprint_decay_proxy_positive_rate": None,
            "repeated_fingerprint_decay_proxy_net": None,
            "gap_signal_runs": 0,
            "gap_resolution_runs": 0,
            "gap_resolution_rate": None,
            "time_to_gap_resolution_proxy_runs": None,
            "time_to_gap_resolution_proxy_s": None,
            "transfer_active_runs": 0,
            "transfer_hit_runs": 0,
            "transfer_hit_rate_proxy": None,
        }

    failed = sum(1 for row in rows if str(row.get("status", "")) == "failed")
    canceled = sum(1 for row in rows if str(row.get("status", "")) == "canceled")
    timed_out = sum(1 for row in rows if str(row.get("status", "")) == "timed_out")
    lesson_writes = [_as_int(row.get("lesson_writes"), 0) for row in rows]
    retrieval_series = [_as_float(row.get("retrieval_help_ratio"), 0.0) for row in rows]
    retrieval_mean = sum(retrieval_series) / float(total)
    retrieval_delta = retrieval_series[-1] - retrieval_series[0] if retrieval_series else None

    first_success_session = None
    first_success_run_index = None
    for idx, row in enumerate(rows):
        if _row_success(row):
            first_success_session = _as_int(row.get("session_id"), -1)
            first_success_run_index = idx + 1
            break
    if first_success_session == -1:
        first_success_session = None

    fingerprint_decay_values: list[float] = []
    for row in rows:
        before = row.get("fingerprint_recurrence_before")
        after = row.get("fingerprint_recurrence_after")
        if before is None or after is None:
            continue
        fingerprint_decay_values.append(_as_float(before, 0.0) - _as_float(after, 0.0))
    fingerprint_decay_mean = None
    fingerprint_decay_positive_rate = None
    fingerprint_decay_net = None
    if fingerprint_decay_values:
        fingerprint_decay_mean = sum(fingerprint_decay_values) / float(len(fingerprint_decay_values))
        fingerprint_decay_positive_rate = (
            sum(1 for value in fingerprint_decay_values if value > 0.0) / float(len(fingerprint_decay_values))
        )
        fingerprint_decay_net = sum(fingerprint_decay_values)

    gap_signal_runs = sum(1 for row in rows if _row_has_gap_signal(row))
    gap_resolution_runs = sum(1 for row in rows if _row_gap_resolved(row))
    gap_resolution_rate = None
    if gap_signal_runs > 0:
        gap_resolution_rate = gap_resolution_runs / float(gap_signal_runs)

    time_to_gap_resolution_proxy_runs = None
    time_to_gap_resolution_proxy_s = None
    first_gap_idx = None
    for idx, row in enumerate(rows):
        if _row_has_gap_signal(row):
            first_gap_idx = idx
            break
    if first_gap_idx is not None:
        for idx in range(first_gap_idx, len(rows)):
            if not _row_gap_resolved(rows[idx]):
                continue
            time_to_gap_resolution_proxy_runs = idx - first_gap_idx + 1
            start_ts = rows[first_gap_idx].get("started_ts")
            end_ts = rows[idx].get("ended_ts")
            if start_ts is not None and end_ts is not None and _as_float(end_ts, 0.0) >= _as_float(start_ts, 0.0):
                time_to_gap_resolution_proxy_s = _as_float(end_ts, 0.0) - _as_float(start_ts, 0.0)
            break

    transfer_active_runs = 0
    transfer_hit_runs = 0
    for row in rows:
        transfer_activations = _as_int(row.get("transfer_lane_activations"), 0)
        if transfer_activations <= 0:
            continue
        transfer_active_runs += 1
        # Hit proxy: transfer lane activated and the run either succeeded or
        # showed non-zero retrieval-help signal.
        if _row_success(row) or _as_float(row.get("retrieval_help_ratio"), 0.0) > 0.0:
            transfer_hit_runs += 1
    transfer_hit_rate_proxy = None
    if transfer_active_runs > 0:
        transfer_hit_rate_proxy = transfer_hit_runs / float(transfer_active_runs)

    return {
        "runs": total,
        "fail_rate": failed / float(total),
        "cancel_rate": canceled / float(total),
        "timeout_rate": timed_out / float(total),
        "lesson_writes_total": sum(lesson_writes),
        "lesson_write_runs": sum(1 for value in lesson_writes if value > 0),
        "retrieval_help_ratio_mean": retrieval_mean,
        "retrieval_help_trend_delta": retrieval_delta,
        "first_success_session": first_success_session,
        "first_success_run_index": first_success_run_index,
        "repeated_fingerprint_decay_proxy_mean": fingerprint_decay_mean,
        "repeated_fingerprint_decay_proxy_positive_rate": fingerprint_decay_positive_rate,
        "repeated_fingerprint_decay_proxy_net": fingerprint_decay_net,
        "gap_signal_runs": gap_signal_runs,
        "gap_resolution_runs": gap_resolution_runs,
        "gap_resolution_rate": gap_resolution_rate,
        "time_to_gap_resolution_proxy_runs": time_to_gap_resolution_proxy_runs,
        "time_to_gap_resolution_proxy_s": time_to_gap_resolution_proxy_s,
        "transfer_active_runs": transfer_active_runs,
        "transfer_hit_runs": transfer_hit_runs,
        "transfer_hit_rate_proxy": transfer_hit_rate_proxy,
    }


def _format_optional(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{_as_float(value):.3f}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize recent run health from the observability ledger.")
    ap.add_argument("--sessions-root", default=str(SESSIONS_ROOT))
    ap.add_argument("--last", type=int, default=20, help="Number of most recent ledger runs to summarize.")
    ap.add_argument("--output-json", default="", help="Optional path for structured output.")
    args = ap.parse_args()

    sessions_root = Path(args.sessions_root)
    rows = load_recent_runs(sessions_root=sessions_root, last_n=max(0, int(args.last)))
    summary = summarize_run_health(rows)
    payload = {"summary": summary, "rows": rows}

    print("Run Health")
    print(
        "runs={runs} fail_rate={fail:.2%} cancel_rate={cancel:.2%} timeout_rate={timeout:.2%}".format(
            runs=int(summary["runs"]),
            fail=float(summary["fail_rate"]),
            cancel=float(summary["cancel_rate"]),
            timeout=float(summary["timeout_rate"]),
        )
    )
    print(
        "lesson_writes_total={total} lesson_write_runs={runs}".format(
            total=int(summary["lesson_writes_total"]),
            runs=int(summary["lesson_write_runs"]),
        )
    )
    print(
        "retrieval_help_mean={mean} retrieval_help_trend_delta={delta}".format(
            mean=_format_optional(summary["retrieval_help_ratio_mean"]),
            delta=_format_optional(summary["retrieval_help_trend_delta"]),
        )
    )
    print(
        "first_success_session={session} first_success_run_index={run_idx}".format(
            session=summary["first_success_session"] if summary["first_success_session"] is not None else "n/a",
            run_idx=summary["first_success_run_index"] if summary["first_success_run_index"] is not None else "n/a",
        )
    )
    print(
        "fingerprint_decay_mean={mean} fingerprint_decay_positive_rate={positive} fingerprint_decay_net={net}".format(
            mean=_format_optional(summary["repeated_fingerprint_decay_proxy_mean"]),
            positive=_format_optional(summary["repeated_fingerprint_decay_proxy_positive_rate"]),
            net=_format_optional(summary["repeated_fingerprint_decay_proxy_net"]),
        )
    )
    print(
        "gap_signal_runs={signal} gap_resolution_runs={resolved} gap_resolution_rate={rate} gap_resolution_runs_to_fix={runs} gap_resolution_time_s={seconds}".format(
            signal=int(summary["gap_signal_runs"]),
            resolved=int(summary["gap_resolution_runs"]),
            rate=_format_optional(summary["gap_resolution_rate"]),
            runs=summary["time_to_gap_resolution_proxy_runs"]
            if summary["time_to_gap_resolution_proxy_runs"] is not None
            else "n/a",
            seconds=_format_optional(summary["time_to_gap_resolution_proxy_s"]),
        )
    )
    print(
        "transfer_active_runs={active} transfer_hit_runs={hit} transfer_hit_rate={rate}".format(
            active=int(summary["transfer_active_runs"]),
            hit=int(summary["transfer_hit_runs"]),
            rate=_format_optional(summary["transfer_hit_rate_proxy"]),
        )
    )

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        print(f"Wrote summary: {output_path}")

    print("\nJSON summary:")
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
