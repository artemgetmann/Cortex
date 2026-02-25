#!/usr/bin/env python3
"""Summarize run health from run_ledger.jsonl and per-session metrics."""
from __future__ import annotations

import argparse
import json
import sys
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
        }

    failed = sum(1 for row in rows if str(row.get("status", "")) == "failed")
    canceled = sum(1 for row in rows if str(row.get("status", "")) == "canceled")
    timed_out = sum(1 for row in rows if str(row.get("status", "")) == "timed_out")
    lesson_writes = [_as_int(row.get("lesson_writes"), 0) for row in rows]
    retrieval_series = [_as_float(row.get("retrieval_help_ratio"), 0.0) for row in rows]
    retrieval_mean = sum(retrieval_series) / float(total)
    retrieval_delta = retrieval_series[-1] - retrieval_series[0] if retrieval_series else None
    return {
        "runs": total,
        "fail_rate": failed / float(total),
        "cancel_rate": canceled / float(total),
        "timeout_rate": timed_out / float(total),
        "lesson_writes_total": sum(lesson_writes),
        "lesson_write_runs": sum(1 for value in lesson_writes if value > 0),
        "retrieval_help_ratio_mean": retrieval_mean,
        "retrieval_help_trend_delta": retrieval_delta,
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
