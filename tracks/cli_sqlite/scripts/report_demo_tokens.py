#!/usr/bin/env python3
"""Summarize token usage for mixed benchmark JSON artifacts.

This script reads one or more wave JSON files produced by run_mixed_benchmark.py
and joins each run row with its session metrics usage payload, then prints:
- per-run token totals
- per-wave aggregate totals
- grand totals

Token fields come from metrics["usage"] entries and include:
- input_tokens
- output_tokens
- cache_read_input_tokens
- cache_creation_input_tokens
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SESSIONS_ROOT = Path(__file__).resolve().parents[1] / "sessions"


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _usage_totals(metrics: dict[str, Any]) -> dict[str, int]:
    usage = metrics.get("usage", [])
    if not isinstance(usage, list):
        usage = []
    out = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    for item in usage:
        if not isinstance(item, dict):
            continue
        out["input_tokens"] += _as_int(item.get("input_tokens"))
        out["output_tokens"] += _as_int(item.get("output_tokens"))
        out["cache_read_input_tokens"] += _as_int(item.get("cache_read_input_tokens"))
        out["cache_creation_input_tokens"] += _as_int(item.get("cache_creation_input_tokens"))
    out["total_visible_tokens"] = out["input_tokens"] + out["output_tokens"]
    out["total_with_cache_tokens"] = out["total_visible_tokens"] + out["cache_read_input_tokens"] + out["cache_creation_input_tokens"]
    return out


def _session_metrics(session_id: int) -> dict[str, Any]:
    metrics_path = SESSIONS_ROOT / f"session-{session_id}" / "metrics.json"
    if not metrics_path.exists():
        return {}
    try:
        return _load_json(metrics_path)
    except Exception:
        return {}


def _sum_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    out = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "total_visible_tokens": 0,
        "total_with_cache_tokens": 0,
    }
    for row in rows:
        for key in out:
            out[key] += _as_int(row.get(key))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Report token usage from mixed benchmark wave JSON outputs.")
    ap.add_argument("--input-json", action="append", required=True, help="Wave JSON path (repeatable).")
    ap.add_argument("--output-json", default="", help="Optional path to write machine-readable token summary.")
    args = ap.parse_args()

    all_rows: list[dict[str, Any]] = []
    wave_summaries: list[dict[str, Any]] = []

    for wave_path_str in args.input_json:
        wave_path = Path(wave_path_str)
        wave_payload = _load_json(wave_path)
        run_rows = wave_payload.get("runs", [])
        if not isinstance(run_rows, list):
            run_rows = []

        enriched_rows: list[dict[str, Any]] = []
        for row in run_rows:
            if not isinstance(row, dict):
                continue
            session_id = _as_int(row.get("session_id"))
            metrics = _session_metrics(session_id)
            tok = _usage_totals(metrics)
            enriched = {
                "wave": wave_path.name,
                "phase": str(row.get("phase", "")),
                "session_id": session_id,
                "passed": bool(row.get("passed", False)),
                "score": float(row.get("score", 0.0) or 0.0),
                "lessons_loaded": _as_int(row.get("lessons_loaded")),
                **tok,
            }
            enriched_rows.append(enriched)
            all_rows.append(enriched)

        wave_totals = _sum_rows(enriched_rows)
        wave_summaries.append(
            {
                "wave": wave_path.name,
                "runs": len(enriched_rows),
                **wave_totals,
            }
        )

    print("\n=== Token Usage Per Run ===")
    print(
        f"{'Wave':<30} {'Phase':<25} {'Session':>7} {'Pass':>4} {'LIn':>4} "
        f"{'InTok':>8} {'OutTok':>8} {'CacheR':>8} {'CacheC':>8} {'AllTok':>9}"
    )
    for row in all_rows:
        print(
            f"{row['wave']:<30} {row['phase']:<25} {row['session_id']:>7} "
            f"{('Y' if row['passed'] else 'N'):>4} {row['lessons_loaded']:>4} "
            f"{row['input_tokens']:>8} {row['output_tokens']:>8} "
            f"{row['cache_read_input_tokens']:>8} {row['cache_creation_input_tokens']:>8} "
            f"{row['total_with_cache_tokens']:>9}"
        )

    print("\n=== Token Usage Per Wave ===")
    print(f"{'Wave':<30} {'Runs':>4} {'InTok':>9} {'OutTok':>9} {'CacheR':>9} {'CacheC':>9} {'AllTok':>10}")
    for wave in wave_summaries:
        print(
            f"{wave['wave']:<30} {wave['runs']:>4} {wave['input_tokens']:>9} {wave['output_tokens']:>9} "
            f"{wave['cache_read_input_tokens']:>9} {wave['cache_creation_input_tokens']:>9} "
            f"{wave['total_with_cache_tokens']:>10}"
        )

    grand = _sum_rows(all_rows)
    print("\n=== Token Usage Grand Total ===")
    print(
        json.dumps(
            {
                "runs": len(all_rows),
                **grand,
            },
            indent=2,
            ensure_ascii=True,
        )
    )

    payload = {
        "waves": wave_summaries,
        "runs": all_rows,
        "grand_total": {"runs": len(all_rows), **grand},
    }
    if args.output_json:
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        print(f"\nWrote token report JSON: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
