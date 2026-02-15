#!/usr/bin/env python3
"""Summarize Memory V2 health from benchmark payloads or session metrics."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


TRACK_ROOT = Path(__file__).resolve().parents[1]
SESSIONS_ROOT = TRACK_ROOT / "sessions"


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / float(len(values))


def _load_rows_from_payload(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("runs", [])
    if not isinstance(rows, list):
        return []
    result: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            result.append(row)
    return result


def _rows_from_metrics_files(
    *,
    sessions_root: Path,
    start_session: int | None,
    end_session: int | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for metrics_path in sorted(sessions_root.glob("session-*/metrics.json")):
        try:
            session_id = int(metrics_path.parent.name.split("-")[-1])
        except (TypeError, ValueError):
            continue
        if start_session is not None and session_id < start_session:
            continue
        if end_session is not None and session_id > end_session:
            continue
        try:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(metrics, dict):
            continue
        rows.append(
            {
                "phase": "session_metrics",
                "domain": str(metrics.get("domain", "")),
                "task_id": str(metrics.get("task_id", "")),
                "run": len(rows) + 1,
                "session_id": session_id,
                "passed": bool(metrics.get("eval_passed", False)),
                "score": _as_float(metrics.get("eval_score"), 0.0),
                "steps": _as_int(metrics.get("steps"), 0),
                "tool_errors": _as_int(metrics.get("tool_errors"), 0),
                "fingerprint_recurrence_before": _as_float(metrics.get("v2_fingerprint_recurrence_before"), 0.0),
                "fingerprint_recurrence_after": _as_float(metrics.get("v2_fingerprint_recurrence_after"), 0.0),
                "lesson_activations": _as_int(metrics.get("lesson_activations"), 0),
                "promoted_count": _as_int(metrics.get("v2_promoted"), 0),
                "suppressed_count": _as_int(metrics.get("v2_suppressed"), 0),
                "retrieval_help_ratio": _as_float(metrics.get("v2_retrieval_help_ratio"), 0.0),
            }
        )
    return rows


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "runs": 0,
            "pass_rate": 0.0,
            "mean_score": None,
            "mean_steps": None,
            "mean_tool_errors": None,
            "fingerprint_recurrence_before_mean": None,
            "fingerprint_recurrence_after_mean": None,
            "lesson_activations_total": 0,
            "promoted_total": 0,
            "suppressed_total": 0,
            "retrieval_help_ratio_mean": None,
        }
    pass_count = sum(1 for row in rows if bool(row.get("passed", False)))
    return {
        "runs": len(rows),
        "pass_rate": pass_count / float(len(rows)),
        "mean_score": _safe_mean([_as_float(row.get("score"), 0.0) for row in rows]),
        "mean_steps": _safe_mean([float(_as_int(row.get("steps"), 0)) for row in rows]),
        "mean_tool_errors": _safe_mean([float(_as_int(row.get("tool_errors"), 0)) for row in rows]),
        "fingerprint_recurrence_before_mean": _safe_mean(
            [_as_float(row.get("fingerprint_recurrence_before"), 0.0) for row in rows]
        ),
        "fingerprint_recurrence_after_mean": _safe_mean(
            [_as_float(row.get("fingerprint_recurrence_after"), 0.0) for row in rows]
        ),
        "lesson_activations_total": sum(_as_int(row.get("lesson_activations"), 0) for row in rows),
        "promoted_total": sum(_as_int(row.get("promoted_count"), 0) for row in rows),
        "suppressed_total": sum(_as_int(row.get("suppressed_count"), 0) for row in rows),
        "retrieval_help_ratio_mean": _safe_mean(
            [_as_float(row.get("retrieval_help_ratio"), 0.0) for row in rows]
        ),
    }


def _format_optional(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{_as_float(value):.3f}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Report Memory V2 health from benchmark/session outputs")
    ap.add_argument("--input-json", nargs="*", default=[], help="Benchmark JSON payload(s) from run_memory_stability.py")
    ap.add_argument("--sessions-root", default=str(SESSIONS_ROOT))
    ap.add_argument("--start-session", type=int, default=None)
    ap.add_argument("--end-session", type=int, default=None)
    ap.add_argument("--output-json", default="", help="Optional path for summary JSON")
    args = ap.parse_args()

    rows: list[dict[str, Any]] = []
    if args.input_json:
        for value in args.input_json:
            path = Path(value)
            if not path.exists():
                continue
            rows.extend(_load_rows_from_payload(path))
    else:
        rows = _rows_from_metrics_files(
            sessions_root=Path(args.sessions_root),
            start_session=args.start_session,
            end_session=args.end_session,
        )

    summary = _aggregate(rows)
    payload = {"summary": summary, "rows": rows}

    print("Memory V2 Health")
    print(
        "runs={runs} pass_rate={pass_rate:.2%} score={score} steps={steps} tool_errors={errors}".format(
            runs=summary["runs"],
            pass_rate=float(summary["pass_rate"]),
            score=_format_optional(summary["mean_score"]),
            steps=_format_optional(summary["mean_steps"]),
            errors=_format_optional(summary["mean_tool_errors"]),
        )
    )
    print(
        "fingerprint_before={before} fingerprint_after={after} activations={activations} promoted={promoted} "
        "suppressed={suppressed} retrieval_help={ratio}".format(
            before=_format_optional(summary["fingerprint_recurrence_before_mean"]),
            after=_format_optional(summary["fingerprint_recurrence_after_mean"]),
            activations=int(summary["lesson_activations_total"]),
            promoted=int(summary["promoted_total"]),
            suppressed=int(summary["suppressed_total"]),
            ratio=_format_optional(summary["retrieval_help_ratio_mean"]),
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
