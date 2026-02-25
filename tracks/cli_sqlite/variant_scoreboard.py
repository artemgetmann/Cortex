from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from tracks.cli_sqlite.run_observability import append_jsonl, read_jsonl_rows, variant_scoreboard_path


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


def _clamp_01(value: float) -> float:
    if value <= 0.0:
        return 0.0
    if value >= 1.0:
        return 1.0
    return float(value)


def _first_present(mapping: dict[str, Any], keys: list[str]) -> Any | None:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def usage_totals(metrics: dict[str, Any]) -> dict[str, int]:
    usage = metrics.get("usage", [])
    if not isinstance(usage, list):
        usage = []
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    for item in usage:
        if not isinstance(item, dict):
            continue
        totals["input_tokens"] += _as_int(item.get("input_tokens"))
        totals["output_tokens"] += _as_int(item.get("output_tokens"))
        totals["cache_read_input_tokens"] += _as_int(item.get("cache_read_input_tokens"))
        totals["cache_creation_input_tokens"] += _as_int(item.get("cache_creation_input_tokens"))
    totals["total_visible_tokens"] = totals["input_tokens"] + totals["output_tokens"]
    totals["total_with_cache_tokens"] = (
        totals["total_visible_tokens"]
        + totals["cache_read_input_tokens"]
        + totals["cache_creation_input_tokens"]
    )
    if totals["total_with_cache_tokens"] <= 0:
        fallback_keys = [
            "total_with_cache_tokens",
            "total_visible_tokens",
            "token_estimate",
            "tokens_est",
        ]
        fallback = _as_int(_first_present(metrics, fallback_keys), default=0)
        if fallback > 0:
            totals["total_with_cache_tokens"] = fallback
            if totals["total_visible_tokens"] <= 0:
                totals["total_visible_tokens"] = fallback
    return totals


def resolve_runtime_variant(
    *,
    sessions_root: Path,
    session_id: int,
    default_variant_id: str = "default",
) -> tuple[str, str]:
    variant_spec_path = sessions_root / f"session-{int(session_id):03d}" / "variant_spec.json"
    if not variant_spec_path.exists():
        return str(default_variant_id), "default_fallback"
    try:
        payload = json.loads(variant_spec_path.read_text(encoding="utf-8"))
    except Exception:
        return str(default_variant_id), "default_fallback"
    if not isinstance(payload, dict):
        return str(default_variant_id), "default_fallback"
    variant_id = str(payload.get("variant_id", "")).strip()
    if not variant_id:
        return str(default_variant_id), "default_fallback"
    return variant_id, "runtime_spec"


def build_variant_score_row(
    *,
    run_source: str,
    session_id: int,
    task_id: str,
    domain: str,
    variant_id: str,
    variant_source: str,
    elapsed_s: float,
    metrics: dict[str, Any],
    run_index: int | None = None,
    phase: str | None = None,
    arm_id: str | None = None,
    variant_family: str | None = None,
) -> dict[str, Any]:
    passed = bool(_first_present(metrics, ["eval_passed", "passed", "judge_passed"]) or False)
    eval_score = _clamp_01(_as_float(_first_present(metrics, ["eval_score", "score", "judge_score"]), default=0.0))
    steps = _as_int(_first_present(metrics, ["steps"]), default=0)
    tool_errors = _as_int(_first_present(metrics, ["tool_errors", "errors"]), default=0)
    tokens = usage_totals(metrics)
    total_tokens = _as_int(tokens.get("total_with_cache_tokens"), default=0)

    quality_score = _clamp_01((0.8 * eval_score) + (0.2 if passed else 0.0))
    speed_score = 1.0 / (1.0 + (max(0.0, float(elapsed_s)) / 30.0) + (max(0, int(steps)) / 12.0))
    cost_score = 1.0 / (1.0 + (max(0, total_tokens) / 3000.0) + (max(0, int(tool_errors)) / 4.0))
    variant_score = (0.6 * quality_score) + (0.25 * speed_score) + (0.15 * cost_score)

    row = {
        "ts": time.time(),
        "run_source": str(run_source),
        "session_id": int(session_id),
        "task_id": str(task_id),
        "domain": str(domain),
        "phase": str(phase or ""),
        "arm_id": str(arm_id or ""),
        "run_index": int(run_index) if run_index is not None else None,
        "variant_family": str(variant_family or task_id),
        "variant_id": str(variant_id),
        "variant_source": str(variant_source),
        "passed": bool(passed),
        "eval_score": round(eval_score, 6),
        "elapsed_s": round(max(0.0, float(elapsed_s)), 6),
        "steps": int(steps),
        "tool_errors": int(tool_errors),
        "input_tokens": int(tokens["input_tokens"]),
        "output_tokens": int(tokens["output_tokens"]),
        "cache_read_input_tokens": int(tokens["cache_read_input_tokens"]),
        "cache_creation_input_tokens": int(tokens["cache_creation_input_tokens"]),
        "total_visible_tokens": int(tokens["total_visible_tokens"]),
        "total_with_cache_tokens": int(tokens["total_with_cache_tokens"]),
        "quality_score": round(quality_score, 6),
        "speed_score": round(speed_score, 6),
        "cost_score": round(cost_score, 6),
        "variant_score": round(variant_score, 6),
        "raw_metrics": {
            "passed": bool(passed),
            "eval_score": round(eval_score, 6),
            "elapsed_s": round(max(0.0, float(elapsed_s)), 6),
            "steps": int(steps),
            "tool_errors": int(tool_errors),
            "lessons_loaded": _as_int(_first_present(metrics, ["lessons_loaded", "v2_lessons_loaded"]), default=0),
            "lessons_generated": _as_int(_first_present(metrics, ["lessons_generated", "v2_lessons_generated"]), default=0),
            "input_tokens": int(tokens["input_tokens"]),
            "output_tokens": int(tokens["output_tokens"]),
            "total_with_cache_tokens": int(tokens["total_with_cache_tokens"]),
        },
    }
    return row


def append_variant_score_row(*, sessions_root: Path, row: dict[str, Any]) -> None:
    append_jsonl(variant_scoreboard_path(sessions_root=sessions_root), row)


def append_variant_score_entry(
    *,
    sessions_root: Path,
    run_source: str,
    session_id: int,
    task_id: str,
    domain: str,
    variant_id: str,
    variant_source: str,
    elapsed_s: float,
    metrics: dict[str, Any],
    run_index: int | None = None,
    phase: str | None = None,
    arm_id: str | None = None,
    variant_family: str | None = None,
) -> dict[str, Any]:
    row = build_variant_score_row(
        run_source=run_source,
        session_id=session_id,
        task_id=task_id,
        domain=domain,
        variant_id=variant_id,
        variant_source=variant_source,
        elapsed_s=elapsed_s,
        metrics=metrics,
        run_index=run_index,
        phase=phase,
        arm_id=arm_id,
        variant_family=variant_family,
    )
    append_variant_score_row(sessions_root=sessions_root, row=row)
    return row


def read_variant_score_rows(*, sessions_root: Path) -> list[dict[str, Any]]:
    return read_jsonl_rows(variant_scoreboard_path(sessions_root=sessions_root))


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values) / float(len(values)))


def _row_float(row: dict[str, Any], key: str) -> float:
    return _as_float(row.get(key), default=0.0)


def _row_int(row: dict[str, Any], key: str) -> int:
    return _as_int(row.get(key), default=0)


def rank_variants(
    rows: list[dict[str, Any]],
    *,
    variant_family: str,
) -> list[dict[str, Any]]:
    family = str(variant_family).strip()
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("variant_family", "")).strip() != family:
            continue
        if not str(row.get("variant_id", "")).strip():
            continue
        filtered.append(row)
    by_variant: dict[str, list[dict[str, Any]]] = {}
    for row in filtered:
        variant_id = str(row.get("variant_id", "")).strip()
        by_variant.setdefault(variant_id, []).append(row)

    aggregates: list[dict[str, Any]] = []
    for variant_id in sorted(by_variant):
        group = by_variant[variant_id]
        variant_scores = [_row_float(row, "variant_score") for row in group]
        quality_scores = [_row_float(row, "quality_score") for row in group]
        speed_scores = [_row_float(row, "speed_score") for row in group]
        cost_scores = [_row_float(row, "cost_score") for row in group]
        elapsed_values = [_row_float(row, "elapsed_s") for row in group]
        step_values = [float(_row_int(row, "steps")) for row in group]
        token_values = [float(_row_int(row, "total_with_cache_tokens")) for row in group]
        tool_error_values = [float(_row_int(row, "tool_errors")) for row in group]
        pass_rate = _mean([1.0 if bool(row.get("passed", False)) else 0.0 for row in group])
        latest_session = max(_row_int(row, "session_id") for row in group) if group else 0
        aggregates.append(
            {
                "variant_family": family,
                "variant_id": variant_id,
                "runs": len(group),
                "pass_rate": round(pass_rate, 6),
                "mean_variant_score": round(_mean(variant_scores), 6),
                "mean_quality_score": round(_mean(quality_scores), 6),
                "mean_speed_score": round(_mean(speed_scores), 6),
                "mean_cost_score": round(_mean(cost_scores), 6),
                "mean_elapsed_s": round(_mean(elapsed_values), 6),
                "mean_steps": round(_mean(step_values), 6),
                "mean_total_with_cache_tokens": round(_mean(token_values), 6),
                "mean_tool_errors": round(_mean(tool_error_values), 6),
                "latest_session_id": latest_session,
            }
        )

    return sorted(
        aggregates,
        key=lambda item: (
            -_as_float(item.get("mean_variant_score"), default=0.0),
            -_as_float(item.get("pass_rate"), default=0.0),
            -_as_float(item.get("mean_quality_score"), default=0.0),
            -_as_float(item.get("mean_speed_score"), default=0.0),
            -_as_float(item.get("mean_cost_score"), default=0.0),
            _as_float(item.get("mean_elapsed_s"), default=0.0),
            _as_float(item.get("mean_steps"), default=0.0),
            _as_float(item.get("mean_total_with_cache_tokens"), default=0.0),
            _as_float(item.get("mean_tool_errors"), default=0.0),
            -_as_int(item.get("runs"), default=0),
            str(item.get("variant_id", "")),
        ),
    )


def select_best_variant(
    rows: list[dict[str, Any]],
    *,
    variant_family: str,
) -> dict[str, Any] | None:
    ranked = rank_variants(rows, variant_family=variant_family)
    if not ranked:
        return None
    return ranked[0]


def select_best_variant_from_scoreboard(
    *,
    sessions_root: Path,
    variant_family: str,
) -> dict[str, Any] | None:
    rows = read_variant_score_rows(sessions_root=sessions_root)
    return select_best_variant(rows, variant_family=variant_family)
