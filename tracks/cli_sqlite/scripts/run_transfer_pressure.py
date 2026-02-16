#!/usr/bin/env python3
"""Benchmark strict-only vs auto-transfer under weak/no strict-match pressure.

This runner intentionally creates a transfer-pressure setup:
1) seed lessons in one domain/task (e.g. gridtool aggregate_report)
2) evaluate another domain/task (e.g. fluxtool holdout) from the same seed state
   with two retrieval policies:
   - strict_only: transfer lane forced off
   - auto_transfer: transfer lane on auto policy

The benchmark reports:
- transfer activation totals/rates,
- retrieval help ratio,
- contamination indicators (suppression, recurrence increase, transfer-failure pressure).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from config import load_config
from tracks.cli_sqlite import agent_cli


TRACK_ROOT = Path(__file__).resolve().parents[1]
LEARNING_ROOT = TRACK_ROOT / "learning"
DEFAULT_LESSONS_PATH = LEARNING_ROOT / "lessons.jsonl"
DEFAULT_LESSONS_V2_PATH = LEARNING_ROOT / "lessons_v2.jsonl"
DEFAULT_MEMORY_EVENTS_PATH = LEARNING_ROOT / "memory_events.jsonl"
DEFAULT_ESCALATION_PATH = LEARNING_ROOT / "critic_escalation_state.json"

DEFAULT_LEARNING_MODE = str(getattr(agent_cli, "DEFAULT_LEARNING_MODE", "legacy"))
LEARNING_MODES = tuple(getattr(agent_cli, "LEARNING_MODES", ("legacy", "strict")))
DEFAULT_EXECUTOR_MODEL = str(getattr(agent_cli, "DEFAULT_EXECUTOR_MODEL", "claude-haiku-4-5"))
DEFAULT_CRITIC_MODEL = str(getattr(agent_cli, "DEFAULT_CRITIC_MODEL", "claude-haiku-4-5"))
DEFAULT_TRANSFER_MAX_RESULTS = int(
    getattr(agent_cli, "DEFAULT_TRANSFER_RETRIEVAL_MAX_RESULTS", 1)
)
DEFAULT_TRANSFER_SCORE_WEIGHT = float(
    getattr(agent_cli, "DEFAULT_TRANSFER_RETRIEVAL_SCORE_WEIGHT", 0.35)
)

run_cli_agent = agent_cli.run_cli_agent
LESSONS_PATH = Path(getattr(agent_cli, "LESSONS_PATH", DEFAULT_LESSONS_PATH))
LESSONS_V2_PATH = Path(getattr(agent_cli, "LESSONS_V2_PATH", DEFAULT_LESSONS_V2_PATH))
MEMORY_EVENTS_PATH = Path(getattr(agent_cli, "MEMORY_EVENTS_PATH", DEFAULT_MEMORY_EVENTS_PATH))
ESCALATION_STATE_PATH = Path(getattr(agent_cli, "ESCALATION_STATE_PATH", DEFAULT_ESCALATION_PATH))


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


def _clear_lessons_store() -> None:
    # Full reset keeps the pressure scenario honest by removing prior domain
    # memory that could create strict-lane matches on the target domain.
    for path in (LESSONS_PATH, LESSONS_V2_PATH, MEMORY_EVENTS_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")


def _clear_escalation() -> None:
    if ESCALATION_STATE_PATH.exists():
        ESCALATION_STATE_PATH.unlink()


def _snapshot_learning_state() -> dict[str, str | None]:
    # Snapshot only files that influence retrieval and replayability for this
    # benchmark. Session artifacts are left untouched.
    snapshot: dict[str, str | None] = {}
    for path in (LESSONS_PATH, LESSONS_V2_PATH, MEMORY_EVENTS_PATH):
        if path.exists():
            snapshot[str(path)] = path.read_text(encoding="utf-8")
        else:
            snapshot[str(path)] = None
    return snapshot


def _restore_learning_state(snapshot: dict[str, str | None]) -> None:
    for raw_path, content in snapshot.items():
        path = Path(raw_path)
        if content is None:
            if path.exists():
                path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _extract_row(
    *,
    arm: str,
    domain: str,
    task_id: str,
    run_idx: int,
    session_id: int,
    elapsed_s: float,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    # Prefer v2 fields when present; older aliases are preserved for
    # compatibility with historical sessions.
    lesson_activations = _as_int(
        metrics.get("v2_lesson_activations", metrics.get("lesson_activations", 0)),
        default=0,
    )
    transfer_activations = _as_int(
        metrics.get("v2_transfer_lane_activations", 0),
        default=0,
    )
    strict_activations = max(0, lesson_activations - transfer_activations)
    fp_before = _as_float(metrics.get("v2_fingerprint_recurrence_before", 0.0), default=0.0)
    fp_after = _as_float(metrics.get("v2_fingerprint_recurrence_after", 0.0), default=0.0)
    retrieval_help_ratio = _as_float(metrics.get("v2_retrieval_help_ratio", 0.0), default=0.0)

    return {
        "arm": arm,
        "domain": domain,
        "task_id": task_id,
        "run": run_idx,
        "session_id": session_id,
        "passed": bool(metrics.get("eval_passed", False)),
        "score": _as_float(metrics.get("eval_score", 0.0), default=0.0),
        "steps": _as_int(metrics.get("steps", 0), default=0),
        "tool_errors": _as_int(metrics.get("tool_errors", 0), default=0),
        "lesson_activations": lesson_activations,
        "strict_lane_activations": strict_activations,
        "transfer_lane_activations": transfer_activations,
        "retrieval_help_ratio": retrieval_help_ratio,
        "fingerprint_recurrence_before": fp_before,
        "fingerprint_recurrence_after": fp_after,
        "promoted_count": _as_int(metrics.get("v2_promoted", 0), default=0),
        "suppressed_count": _as_int(metrics.get("v2_suppressed", 0), default=0),
        "validation_retry_attempts": _as_int(metrics.get("tool_validation_retry_attempts", 0), default=0),
        "validation_retry_capped_events": _as_int(metrics.get("tool_validation_retry_capped_events", 0), default=0),
        "transfer_policy": str(metrics.get("v2_transfer_retrieval_policy", "")),
        "transfer_enabled": bool(metrics.get("v2_transfer_retrieval_enabled", False)),
        "transfer_only_activation": transfer_activations > 0 and strict_activations == 0,
        "mixed_activation": transfer_activations > 0 and strict_activations > 0,
        "recurrence_increase": fp_after > fp_before,
        "elapsed_s": round(elapsed_s, 3),
    }


def _aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "runs": 0,
            "pass_rate": 0.0,
            "mean_score": None,
            "mean_steps": None,
            "mean_tool_errors": None,
            "lesson_activations_total": 0,
            "strict_lane_activations_total": 0,
            "transfer_lane_activations_total": 0,
            "transfer_activation_rate": 0.0,
            "retrieval_help_ratio_weighted": None,
            "retrieval_help_ratio_mean": None,
            "suppressed_total": 0,
            "promoted_total": 0,
            "fingerprint_recurrence_before_mean": None,
            "fingerprint_recurrence_after_mean": None,
            "fingerprint_recurrence_delta_mean": None,
            "validation_retry_attempts_total": 0,
            "validation_retry_capped_events_total": 0,
            "transfer_active_session_rate": 0.0,
            "transfer_only_session_rate": 0.0,
            "mixed_activation_session_rate": 0.0,
            "transfer_failure_rate": None,
            "transfer_error_mean": None,
            "transfer_suppression_rate": None,
            "contamination_session_rate": 0.0,
            "elapsed_s_total": 0.0,
        }

    runs = len(rows)
    pass_count = sum(1 for row in rows if bool(row.get("passed", False)))
    lesson_total = sum(_as_int(row.get("lesson_activations", 0), default=0) for row in rows)
    strict_total = sum(_as_int(row.get("strict_lane_activations", 0), default=0) for row in rows)
    transfer_total = sum(_as_int(row.get("transfer_lane_activations", 0), default=0) for row in rows)

    transfer_rows = [row for row in rows if _as_int(row.get("transfer_lane_activations", 0), default=0) > 0]
    transfer_run_count = len(transfer_rows)
    transfer_fail_count = sum(1 for row in transfer_rows if not bool(row.get("passed", False)))
    transfer_suppressed_runs = sum(
        1 for row in transfer_rows if _as_int(row.get("suppressed_count", 0), default=0) > 0
    )

    recurrence_increase_count = sum(1 for row in rows if bool(row.get("recurrence_increase", False)))
    # Contamination proxy (conservative): either explicit suppression was needed
    # or recurrence increased after retrieval actions in the run.
    contamination_runs = sum(
        1
        for row in rows
        if (
            _as_int(row.get("suppressed_count", 0), default=0) > 0
            or bool(row.get("recurrence_increase", False))
        )
    )

    weighted_help_numerator = 0.0
    weighted_help_denominator = 0
    for row in rows:
        activations = _as_int(row.get("lesson_activations", 0), default=0)
        ratio = _as_float(row.get("retrieval_help_ratio", 0.0), default=0.0)
        if activations <= 0:
            continue
        weighted_help_numerator += ratio * float(activations)
        weighted_help_denominator += activations

    retrieval_help_ratio_weighted = None
    if weighted_help_denominator > 0:
        retrieval_help_ratio_weighted = weighted_help_numerator / float(weighted_help_denominator)

    retrieval_ratio_values = [
        _as_float(row.get("retrieval_help_ratio", 0.0), default=0.0)
        for row in rows
    ]

    fp_before_values = [
        _as_float(row.get("fingerprint_recurrence_before", 0.0), default=0.0)
        for row in rows
    ]
    fp_after_values = [
        _as_float(row.get("fingerprint_recurrence_after", 0.0), default=0.0)
        for row in rows
    ]

    fp_before_mean = _safe_mean(fp_before_values)
    fp_after_mean = _safe_mean(fp_after_values)
    fp_delta = None
    if fp_before_mean is not None and fp_after_mean is not None:
        fp_delta = fp_after_mean - fp_before_mean

    transfer_fail_rate = None
    transfer_error_mean = None
    transfer_suppression_rate = None
    if transfer_run_count > 0:
        transfer_fail_rate = transfer_fail_count / float(transfer_run_count)
        transfer_error_mean = _safe_mean(
            [_as_float(row.get("tool_errors", 0), default=0.0) for row in transfer_rows]
        )
        transfer_suppression_rate = transfer_suppressed_runs / float(transfer_run_count)

    return {
        "runs": runs,
        "pass_rate": pass_count / float(runs),
        "mean_score": _safe_mean([_as_float(row.get("score", 0.0), default=0.0) for row in rows]),
        "mean_steps": _safe_mean([_as_float(row.get("steps", 0), default=0.0) for row in rows]),
        "mean_tool_errors": _safe_mean([_as_float(row.get("tool_errors", 0), default=0.0) for row in rows]),
        "lesson_activations_total": lesson_total,
        "strict_lane_activations_total": strict_total,
        "transfer_lane_activations_total": transfer_total,
        "transfer_activation_rate": (
            transfer_total / float(lesson_total) if lesson_total > 0 else 0.0
        ),
        "retrieval_help_ratio_weighted": retrieval_help_ratio_weighted,
        "retrieval_help_ratio_mean": _safe_mean(retrieval_ratio_values),
        "suppressed_total": sum(_as_int(row.get("suppressed_count", 0), default=0) for row in rows),
        "promoted_total": sum(_as_int(row.get("promoted_count", 0), default=0) for row in rows),
        "fingerprint_recurrence_before_mean": fp_before_mean,
        "fingerprint_recurrence_after_mean": fp_after_mean,
        "fingerprint_recurrence_delta_mean": fp_delta,
        "validation_retry_attempts_total": sum(
            _as_int(row.get("validation_retry_attempts", 0), default=0) for row in rows
        ),
        "validation_retry_capped_events_total": sum(
            _as_int(row.get("validation_retry_capped_events", 0), default=0) for row in rows
        ),
        "transfer_active_session_rate": transfer_run_count / float(runs),
        "transfer_only_session_rate": (
            sum(1 for row in rows if bool(row.get("transfer_only_activation", False))) / float(runs)
        ),
        "mixed_activation_session_rate": (
            sum(1 for row in rows if bool(row.get("mixed_activation", False))) / float(runs)
        ),
        "transfer_failure_rate": transfer_fail_rate,
        "transfer_error_mean": transfer_error_mean,
        "transfer_suppression_rate": transfer_suppression_rate,
        "contamination_session_rate": contamination_runs / float(runs),
        "elapsed_s_total": sum(_as_float(row.get("elapsed_s", 0.0), default=0.0) for row in rows),
        "recurrence_increase_session_rate": recurrence_increase_count / float(runs),
    }


def _format_optional(value: float | None, precision: int = 3) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.{precision}f}"


def _run_phase(
    *,
    cfg: Any,
    arm: str,
    domain: str,
    task_id: str,
    sessions: int,
    start_session: int,
    max_steps: int,
    learning_mode: str,
    model_executor: str,
    model_critic: str,
    model_judge: str | None,
    bootstrap: bool,
    cryptic_errors: bool,
    semi_helpful_errors: bool,
    mixed_errors: bool,
    posttask_mode: str,
    posttask_learn: bool,
    enable_transfer_retrieval: bool,
    transfer_retrieval_max_results: int,
    transfer_retrieval_score_weight: float,
    verbose: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx in range(sessions):
        run_idx = idx + 1
        session_id = start_session + idx
        print(
            f"  [{arm}] run {run_idx}/{sessions} session={session_id} "
            f"domain={domain} task={task_id}"
        )
        t0 = time.time()
        result = run_cli_agent(
            cfg=cfg,
            task_id=task_id,
            task=None,
            session_id=session_id,
            max_steps=max_steps,
            domain=domain,
            learning_mode=learning_mode,
            model_executor=model_executor,
            model_critic=model_critic,
            model_judge=model_judge,
            posttask_mode=posttask_mode,
            posttask_learn=posttask_learn,
            memory_v2_demo_mode=False,
            verbose=verbose,
            auto_escalate_critic=True,
            escalation_score_threshold=0.75,
            escalation_consecutive_runs=2,
            require_skill_read=not bootstrap,
            opaque_tools=False,
            bootstrap=bootstrap,
            cryptic_errors=cryptic_errors,
            semi_helpful_errors=semi_helpful_errors,
            mixed_errors=mixed_errors,
            enable_transfer_retrieval=enable_transfer_retrieval,
            transfer_retrieval_max_results=transfer_retrieval_max_results,
            transfer_retrieval_score_weight=transfer_retrieval_score_weight,
        )
        row = _extract_row(
            arm=arm,
            domain=domain,
            task_id=task_id,
            run_idx=run_idx,
            session_id=session_id,
            elapsed_s=time.time() - t0,
            metrics=result.metrics if isinstance(result.metrics, dict) else {},
        )
        rows.append(row)

        status = "PASS" if row["passed"] else "FAIL"
        print(
            f"    [{status}] score={row['score']:.2f} steps={row['steps']} "
            f"errors={row['tool_errors']} strict_act={row['strict_lane_activations']} "
            f"transfer_act={row['transfer_lane_activations']} "
            f"help={row['retrieval_help_ratio']:.2f} "
            f"suppressed={row['suppressed_count']} "
            f"fp_delta={row['fingerprint_recurrence_after'] - row['fingerprint_recurrence_before']:+.2f} "
            f"({row['elapsed_s']:.2f}s)"
        )
    return rows


def _compute_deltas(
    *,
    strict_summary: dict[str, Any],
    auto_summary: dict[str, Any],
) -> dict[str, Any]:
    # Delta sign convention: auto_transfer - strict_only.
    keys = [
        "pass_rate",
        "mean_score",
        "mean_steps",
        "mean_tool_errors",
        "transfer_activation_rate",
        "retrieval_help_ratio_weighted",
        "contamination_session_rate",
        "recurrence_increase_session_rate",
    ]
    deltas: dict[str, Any] = {}
    for key in keys:
        left = strict_summary.get(key)
        right = auto_summary.get(key)
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            deltas[key] = None
            continue
        deltas[key] = float(right) - float(left)
    return deltas


def _render_markdown_summary(
    *,
    payload: dict[str, Any],
) -> str:
    config = payload["config"]
    strict_summary = payload["arms"]["strict_only"]["summary"]
    auto_summary = payload["arms"]["auto_transfer"]["summary"]
    deltas = payload["deltas"]
    caveats = payload.get("caveats", [])

    lines = [
        "# Transfer Pressure Benchmark Summary",
        "",
        "## Config",
        "",
        f"- seed_domain: `{config['seed_domain']}`",
        f"- seed_task_id: `{config['seed_task_id']}`",
        f"- pressure_domain: `{config['pressure_domain']}`",
        f"- pressure_task_id: `{config['pressure_task_id']}`",
        f"- learning_mode: `{config['learning_mode']}`",
        f"- seed_sessions: `{config['seed_sessions']}`",
        f"- pressure_sessions: `{config['pressure_sessions']}`",
        f"- freeze_pressure_learning: `{config['freeze_pressure_learning']}`",
        f"- auto_transfer_max_results: `{config['auto_transfer_max_results']}`",
        f"- auto_transfer_score_weight: `{config['auto_transfer_score_weight']}`",
        "",
        "## Arm Metrics",
        "",
        "| arm | pass_rate | mean_score | mean_steps | mean_tool_errors | transfer_act_rate | help_ratio_weighted | contamination_rate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        (
            f"| strict_only | {float(strict_summary['pass_rate']):.2%} | "
            f"{_format_optional(strict_summary.get('mean_score'))} | "
            f"{_format_optional(strict_summary.get('mean_steps'))} | "
            f"{_format_optional(strict_summary.get('mean_tool_errors'))} | "
            f"{float(strict_summary.get('transfer_activation_rate', 0.0)):.2%} | "
            f"{_format_optional(strict_summary.get('retrieval_help_ratio_weighted'))} | "
            f"{float(strict_summary.get('contamination_session_rate', 0.0)):.2%} |"
        ),
        (
            f"| auto_transfer | {float(auto_summary['pass_rate']):.2%} | "
            f"{_format_optional(auto_summary.get('mean_score'))} | "
            f"{_format_optional(auto_summary.get('mean_steps'))} | "
            f"{_format_optional(auto_summary.get('mean_tool_errors'))} | "
            f"{float(auto_summary.get('transfer_activation_rate', 0.0)):.2%} | "
            f"{_format_optional(auto_summary.get('retrieval_help_ratio_weighted'))} | "
            f"{float(auto_summary.get('contamination_session_rate', 0.0)):.2%} |"
        ),
        "",
        "## Delta (auto_transfer - strict_only)",
        "",
        f"- pass_rate: `{_format_optional(deltas.get('pass_rate'), precision=4)}`",
        f"- mean_score: `{_format_optional(deltas.get('mean_score'), precision=4)}`",
        f"- mean_steps: `{_format_optional(deltas.get('mean_steps'), precision=4)}`",
        f"- mean_tool_errors: `{_format_optional(deltas.get('mean_tool_errors'), precision=4)}`",
        f"- transfer_activation_rate: `{_format_optional(deltas.get('transfer_activation_rate'), precision=4)}`",
        f"- retrieval_help_ratio_weighted: `{_format_optional(deltas.get('retrieval_help_ratio_weighted'), precision=4)}`",
        f"- contamination_session_rate: `{_format_optional(deltas.get('contamination_session_rate'), precision=4)}`",
        f"- recurrence_increase_session_rate: `{_format_optional(deltas.get('recurrence_increase_session_rate'), precision=4)}`",
    ]
    if caveats:
        lines.extend(["", "## Caveats", ""])
        for caveat in caveats:
            lines.append(f"- {caveat}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Transfer-pressure benchmark: strict_only vs auto_transfer"
    )
    ap.add_argument("--seed-domain", default="gridtool", choices=["sqlite", "gridtool", "fluxtool", "artic", "shell"])
    ap.add_argument("--seed-task-id", default="aggregate_report")
    ap.add_argument("--pressure-domain", default="fluxtool", choices=["sqlite", "gridtool", "fluxtool", "artic", "shell"])
    ap.add_argument("--pressure-task-id", default="aggregate_report_holdout")
    ap.add_argument("--learning-mode", default=DEFAULT_LEARNING_MODE, choices=LEARNING_MODES)
    ap.add_argument("--seed-sessions", type=int, default=3)
    ap.add_argument("--pressure-sessions", type=int, default=5)
    ap.add_argument("--start-session", type=int, default=18001)
    ap.add_argument("--max-steps", type=int, default=8)
    ap.add_argument("--bootstrap", action="store_true")
    ap.add_argument("--cryptic-errors", action="store_true")
    ap.add_argument("--semi-helpful-errors", action="store_true")
    ap.add_argument("--mixed-errors", action="store_true")
    ap.add_argument("--model-executor", default=DEFAULT_EXECUTOR_MODEL)
    ap.add_argument("--model-critic", default=DEFAULT_CRITIC_MODEL)
    ap.add_argument("--model-judge", default=None)
    ap.add_argument("--posttask-mode", choices=["candidate", "direct"], default="candidate")
    ap.add_argument(
        "--freeze-pressure-learning",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Disable post-task lesson generation during pressure arms to keep strict matches sparse",
    )
    ap.add_argument(
        "--clear-lessons",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Clear lesson stores before seed phase for reproducible pressure conditions",
    )
    ap.add_argument(
        "--auto-transfer-max-results",
        type=int,
        default=DEFAULT_TRANSFER_MAX_RESULTS,
        help="Transfer-lane quota for auto_transfer arm",
    )
    ap.add_argument(
        "--auto-transfer-score-weight",
        type=float,
        default=DEFAULT_TRANSFER_SCORE_WEIGHT,
        help="Transfer-lane score multiplier for auto_transfer arm",
    )
    ap.add_argument("--output-json", default="", help="Optional output path for JSON summary")
    ap.add_argument("--output-md", default="", help="Optional output path for markdown summary")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    caveats: list[str] = []

    if args.seed_domain == args.pressure_domain and args.seed_task_id == args.pressure_task_id:
        caveats.append(
            "Seed and pressure targets are identical; strict matches may be strong and transfer pressure may be weak."
        )
    if not bool(args.clear_lessons):
        caveats.append(
            "clear_lessons=false can preserve prior target-domain lessons, reducing weak/no strict-match pressure."
        )
    if not bool(args.freeze_pressure_learning):
        caveats.append(
            "freeze_pressure_learning=false allows pressure runs to generate same-domain lessons, reducing transfer pressure over time."
        )

    if bool(args.clear_lessons):
        _clear_lessons_store()
    _clear_escalation()

    print(f"\n{'=' * 80}")
    print("  Transfer Pressure Benchmark")
    print(
        f"  seed={args.seed_domain}:{args.seed_task_id} ({args.seed_sessions})  "
        f"pressure={args.pressure_domain}:{args.pressure_task_id} ({args.pressure_sessions})"
    )
    print(
        f"  learning_mode={args.learning_mode} bootstrap={args.bootstrap} max_steps={args.max_steps} "
        f"freeze_pressure_learning={bool(args.freeze_pressure_learning)} clear_lessons={bool(args.clear_lessons)}"
    )
    print(f"{'=' * 80}\n")

    model_executor = args.model_executor.strip() or DEFAULT_EXECUTOR_MODEL
    model_critic = args.model_critic.strip() or DEFAULT_CRITIC_MODEL
    model_judge = args.model_judge.strip() if args.model_judge else None
    auto_transfer_max_results = max(0, int(args.auto_transfer_max_results))
    auto_transfer_score_weight = max(0.0, float(args.auto_transfer_score_weight))

    session_cursor = int(args.start_session)

    print(f"--- Seed phase ({args.seed_sessions} sessions) ---")
    seed_rows = _run_phase(
        cfg=cfg,
        arm="seed",
        domain=args.seed_domain,
        task_id=args.seed_task_id,
        sessions=int(args.seed_sessions),
        start_session=session_cursor,
        max_steps=int(args.max_steps),
        learning_mode=args.learning_mode,
        model_executor=model_executor,
        model_critic=model_critic,
        model_judge=model_judge,
        bootstrap=bool(args.bootstrap),
        cryptic_errors=bool(args.cryptic_errors),
        semi_helpful_errors=bool(args.semi_helpful_errors),
        mixed_errors=bool(args.mixed_errors),
        posttask_mode=args.posttask_mode,
        posttask_learn=True,
        enable_transfer_retrieval=False,
        transfer_retrieval_max_results=0,
        transfer_retrieval_score_weight=auto_transfer_score_weight,
        verbose=bool(args.verbose),
    )
    seed_summary = _aggregate_rows(seed_rows)
    session_cursor += int(args.seed_sessions)
    print()

    # Pressure arms must start from the same learned base to make policy
    # comparison meaningful.
    seed_snapshot = _snapshot_learning_state()

    print(f"--- Pressure arm: strict_only ({args.pressure_sessions} sessions) ---")
    _restore_learning_state(seed_snapshot)
    _clear_escalation()
    strict_rows = _run_phase(
        cfg=cfg,
        arm="strict_only",
        domain=args.pressure_domain,
        task_id=args.pressure_task_id,
        sessions=int(args.pressure_sessions),
        start_session=session_cursor,
        max_steps=int(args.max_steps),
        learning_mode=args.learning_mode,
        model_executor=model_executor,
        model_critic=model_critic,
        model_judge=model_judge,
        bootstrap=bool(args.bootstrap),
        cryptic_errors=bool(args.cryptic_errors),
        semi_helpful_errors=bool(args.semi_helpful_errors),
        mixed_errors=bool(args.mixed_errors),
        posttask_mode=args.posttask_mode,
        posttask_learn=not bool(args.freeze_pressure_learning),
        enable_transfer_retrieval=False,
        transfer_retrieval_max_results=0,
        transfer_retrieval_score_weight=auto_transfer_score_weight,
        verbose=bool(args.verbose),
    )
    strict_summary = _aggregate_rows(strict_rows)
    session_cursor += int(args.pressure_sessions)
    print()

    print(f"--- Pressure arm: auto_transfer ({args.pressure_sessions} sessions) ---")
    _restore_learning_state(seed_snapshot)
    _clear_escalation()
    auto_rows = _run_phase(
        cfg=cfg,
        arm="auto_transfer",
        domain=args.pressure_domain,
        task_id=args.pressure_task_id,
        sessions=int(args.pressure_sessions),
        start_session=session_cursor,
        max_steps=int(args.max_steps),
        learning_mode=args.learning_mode,
        model_executor=model_executor,
        model_critic=model_critic,
        model_judge=model_judge,
        bootstrap=bool(args.bootstrap),
        cryptic_errors=bool(args.cryptic_errors),
        semi_helpful_errors=bool(args.semi_helpful_errors),
        mixed_errors=bool(args.mixed_errors),
        posttask_mode=args.posttask_mode,
        posttask_learn=not bool(args.freeze_pressure_learning),
        enable_transfer_retrieval=False,
        transfer_retrieval_max_results=auto_transfer_max_results,
        transfer_retrieval_score_weight=auto_transfer_score_weight,
        verbose=bool(args.verbose),
    )
    auto_summary = _aggregate_rows(auto_rows)
    print()

    deltas = _compute_deltas(strict_summary=strict_summary, auto_summary=auto_summary)

    print(f"{'=' * 80}")
    print("  Pressure Summary")
    print(f"{'=' * 80}")
    print(
        "  strict_only : pass_rate={pr:.2%} score={score} steps={steps} errors={errs} "
        "transfer_rate={tr:.2%} help={help_} contamination={cont:.2%}".format(
            pr=float(strict_summary["pass_rate"]),
            score=_format_optional(strict_summary.get("mean_score")),
            steps=_format_optional(strict_summary.get("mean_steps")),
            errs=_format_optional(strict_summary.get("mean_tool_errors")),
            tr=float(strict_summary.get("transfer_activation_rate", 0.0)),
            help_=_format_optional(strict_summary.get("retrieval_help_ratio_weighted")),
            cont=float(strict_summary.get("contamination_session_rate", 0.0)),
        )
    )
    print(
        "  auto_transfer: pass_rate={pr:.2%} score={score} steps={steps} errors={errs} "
        "transfer_rate={tr:.2%} help={help_} contamination={cont:.2%}".format(
            pr=float(auto_summary["pass_rate"]),
            score=_format_optional(auto_summary.get("mean_score")),
            steps=_format_optional(auto_summary.get("mean_steps")),
            errs=_format_optional(auto_summary.get("mean_tool_errors")),
            tr=float(auto_summary.get("transfer_activation_rate", 0.0)),
            help_=_format_optional(auto_summary.get("retrieval_help_ratio_weighted")),
            cont=float(auto_summary.get("contamination_session_rate", 0.0)),
        )
    )
    print(
        "  delta(auto-strict): pass_rate={pr:+.2%} score={score} steps={steps} errors={errs} "
        "transfer_rate={tr} help={help_} contamination={cont}".format(
            pr=float(deltas.get("pass_rate", 0.0) or 0.0),
            score=_format_optional(deltas.get("mean_score"), precision=4),
            steps=_format_optional(deltas.get("mean_steps"), precision=4),
            errs=_format_optional(deltas.get("mean_tool_errors"), precision=4),
            tr=_format_optional(deltas.get("transfer_activation_rate"), precision=4),
            help_=_format_optional(deltas.get("retrieval_help_ratio_weighted"), precision=4),
            cont=_format_optional(deltas.get("contamination_session_rate"), precision=4),
        )
    )
    print()

    payload = {
        "config": {
            "seed_domain": args.seed_domain,
            "seed_task_id": args.seed_task_id,
            "pressure_domain": args.pressure_domain,
            "pressure_task_id": args.pressure_task_id,
            "learning_mode": args.learning_mode,
            "seed_sessions": int(args.seed_sessions),
            "pressure_sessions": int(args.pressure_sessions),
            "start_session": int(args.start_session),
            "max_steps": int(args.max_steps),
            "bootstrap": bool(args.bootstrap),
            "cryptic_errors": bool(args.cryptic_errors),
            "semi_helpful_errors": bool(args.semi_helpful_errors),
            "mixed_errors": bool(args.mixed_errors),
            "posttask_mode": args.posttask_mode,
            "freeze_pressure_learning": bool(args.freeze_pressure_learning),
            "clear_lessons": bool(args.clear_lessons),
            "auto_transfer_max_results": auto_transfer_max_results,
            "auto_transfer_score_weight": auto_transfer_score_weight,
        },
        "seed": {
            "summary": seed_summary,
            "runs": seed_rows,
        },
        "arms": {
            "strict_only": {
                "summary": strict_summary,
                "runs": strict_rows,
            },
            "auto_transfer": {
                "summary": auto_summary,
                "runs": auto_rows,
            },
        },
        "deltas": deltas,
        "caveats": caveats,
    }

    if args.output_json:
        output_json_path = Path(args.output_json)
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        output_json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        print(f"Wrote JSON summary: {output_json_path}")

    if args.output_md:
        output_md_path = Path(args.output_md)
        output_md_path.parent.mkdir(parents=True, exist_ok=True)
        output_md_path.write_text(_render_markdown_summary(payload=payload), encoding="utf-8")
        print(f"Wrote markdown summary: {output_md_path}")

    print("\nJSON summary:")
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
