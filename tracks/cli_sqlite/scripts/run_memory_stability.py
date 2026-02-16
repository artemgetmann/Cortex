#!/usr/bin/env python3
"""Run the Memory V2 stability protocol across tool switching.

Protocol:
1) gridtool warmup runs
2) fluxtool interference runs
3) gridtool retention runs

The script prints both a human-readable summary and a JSON payload.
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
DEFAULT_ESCALATION_PATH = LEARNING_ROOT / "critic_escalation_state.json"

DEFAULT_LEARNING_MODE = str(getattr(agent_cli, "DEFAULT_LEARNING_MODE", "legacy"))
LEARNING_MODES = tuple(getattr(agent_cli, "LEARNING_MODES", ("legacy", "strict")))
DEFAULT_EXECUTOR_MODEL = str(getattr(agent_cli, "DEFAULT_EXECUTOR_MODEL", "claude-haiku-4-5"))
DEFAULT_CRITIC_MODEL = str(getattr(agent_cli, "DEFAULT_CRITIC_MODEL", "claude-haiku-4-5"))
run_cli_agent = agent_cli.run_cli_agent
LESSONS_PATH = Path(getattr(agent_cli, "LESSONS_PATH", DEFAULT_LESSONS_PATH))
LESSONS_V2_PATH = Path(getattr(agent_cli, "LESSONS_V2_PATH", LEARNING_ROOT / "lessons_v2.jsonl"))
MEMORY_EVENTS_PATH = Path(getattr(agent_cli, "MEMORY_EVENTS_PATH", LEARNING_ROOT / "memory_events.jsonl"))
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


def _first_present(mapping: dict[str, Any], keys: list[str]) -> Any | None:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _first_int(mapping: dict[str, Any], keys: list[str], default: int = 0) -> int:
    value = _first_present(mapping, keys)
    if value is None:
        return default
    return _as_int(value, default=default)


def _first_float(mapping: dict[str, Any], keys: list[str], default: float = 0.0) -> float:
    value = _first_present(mapping, keys)
    if value is None:
        return default
    return _as_float(value, default=default)


def _first_optional_float(mapping: dict[str, Any], keys: list[str]) -> float | None:
    value = _first_present(mapping, keys)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_fingerprint_recurrence(metrics: dict[str, Any]) -> tuple[float | None, float | None]:
    # Memory V2 key names are still in flux. Read several aliases and nested
    # forms so historical/new payloads remain parseable.
    before = _first_optional_float(
        metrics,
        [
            "fingerprint_recurrence_before",
            "v2_fingerprint_recurrence_before",
            "error_fingerprint_recurrence_before",
            "memory_fingerprint_recurrence_before",
            "fingerprint_before",
            "recurrence_before",
        ],
    )
    after = _first_optional_float(
        metrics,
        [
            "fingerprint_recurrence_after",
            "v2_fingerprint_recurrence_after",
            "error_fingerprint_recurrence_after",
            "memory_fingerprint_recurrence_after",
            "fingerprint_after",
            "recurrence_after",
        ],
    )
    nested = metrics.get("fingerprint_recurrence")
    if isinstance(nested, dict):
        if before is None:
            before = _first_optional_float(
                nested,
                ["before", "pre", "prior", "baseline"],
            )
        if after is None:
            after = _first_optional_float(
                nested,
                ["after", "post", "current"],
            )
    return before, after


def _extract_retrieval_stats(
    metrics: dict[str, Any],
    lesson_activations: int,
) -> tuple[float | None, int, int]:
    ratio = _first_optional_float(
        metrics,
        [
            "retrieval_help_ratio",
            "v2_retrieval_help_ratio",
            "memory_retrieval_help_ratio",
            "lesson_help_ratio",
            "activation_help_ratio",
        ],
    )
    helped = _first_int(
        metrics,
        [
            "retrieval_helped",
            "v2_retrieval_helped",
            "retrieval_helped_count",
            "helped_activations",
            "lesson_activations_helped",
        ],
        default=0,
    )
    total = _first_int(
        metrics,
        [
            "retrieval_activations_total",
            "v2_lesson_activations",
            "retrieval_total",
            "activated_lessons_total",
            "lesson_activations_total",
        ],
        default=0,
    )

    # Fallback: many runs only expose lesson_activations.
    if total <= 0 and lesson_activations > 0:
        total = lesson_activations
    if ratio is None and total > 0:
        ratio = max(0.0, min(1.0, helped / float(total)))
    if ratio is not None and helped <= 0 and total > 0:
        helped = max(0, min(total, int(round(ratio * total))))

    return ratio, helped, total


def _extract_row(
    *,
    phase: str,
    domain: str,
    task_id: str,
    run_idx: int,
    session_id: int,
    elapsed_s: float,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    passed = bool(_first_present(metrics, ["eval_passed", "passed", "judge_passed"]) or False)
    score = _first_float(metrics, ["eval_score", "score", "judge_score"], default=0.0)
    steps = _first_int(metrics, ["steps"], default=0)
    tool_errors = _first_int(metrics, ["tool_errors", "errors"], default=0)
    lesson_activations = _first_int(metrics, ["lesson_activations", "activations"], default=0)
    promoted = _first_int(
        metrics,
        ["v2_promoted", "promoted_count", "lessons_promoted", "memory_promoted", "auto_promotion_applied"],
        default=0,
    )
    suppressed = _first_int(
        metrics,
        ["v2_suppressed", "suppressed_count", "lessons_suppressed", "memory_suppressed"],
        default=0,
    )
    fp_before, fp_after = _extract_fingerprint_recurrence(metrics)
    retrieval_ratio, retrieval_helped, retrieval_total = _extract_retrieval_stats(metrics, lesson_activations)

    return {
        "phase": phase,
        "domain": domain,
        "task_id": task_id,
        "run": run_idx,
        "session_id": session_id,
        "passed": passed,
        "score": score,
        "steps": steps,
        "tool_errors": tool_errors,
        "fingerprint_recurrence_before": fp_before,
        "fingerprint_recurrence_after": fp_after,
        "lesson_activations": lesson_activations,
        "promoted_count": promoted,
        "suppressed_count": suppressed,
        "retrieval_help_ratio": retrieval_ratio,
        "retrieval_helped": retrieval_helped,
        "retrieval_activations_total": retrieval_total,
        "elapsed_s": round(elapsed_s, 3),
    }


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / float(len(values))


def _aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "runs": 0,
            "pass_count": 0,
            "fail_count": 0,
            "pass_rate": 0.0,
            "mean_score": None,
            "mean_steps": None,
            "mean_tool_errors": None,
            "fingerprint_recurrence_before_mean": None,
            "fingerprint_recurrence_after_mean": None,
            "lesson_activations_total": 0,
            "promoted_total": 0,
            "suppressed_total": 0,
            "retrieval_helped_total": 0,
            "retrieval_activations_total": 0,
            "retrieval_help_ratio_weighted": None,
            "elapsed_s_total": 0.0,
        }

    pass_count = sum(1 for row in rows if bool(row.get("passed", False)))
    runs = len(rows)
    fp_before_values = [
        float(value)
        for value in (row.get("fingerprint_recurrence_before") for row in rows)
        if isinstance(value, (int, float))
    ]
    fp_after_values = [
        float(value)
        for value in (row.get("fingerprint_recurrence_after") for row in rows)
        if isinstance(value, (int, float))
    ]

    retrieval_helped_total = sum(_as_int(row.get("retrieval_helped"), default=0) for row in rows)
    retrieval_total_total = sum(_as_int(row.get("retrieval_activations_total"), default=0) for row in rows)
    retrieval_help_ratio_weighted = None
    if retrieval_total_total > 0:
        retrieval_help_ratio_weighted = retrieval_helped_total / float(retrieval_total_total)
    else:
        # Fallback for payloads that expose ratio only.
        ratio_values = [
            float(value)
            for value in (row.get("retrieval_help_ratio") for row in rows)
            if isinstance(value, (int, float))
        ]
        retrieval_help_ratio_weighted = _mean(ratio_values)

    return {
        "runs": runs,
        "pass_count": pass_count,
        "fail_count": runs - pass_count,
        "pass_rate": pass_count / float(runs),
        "mean_score": _mean([_as_float(row.get("score"), default=0.0) for row in rows]),
        "mean_steps": _mean([float(_as_int(row.get("steps"), default=0)) for row in rows]),
        "mean_tool_errors": _mean([float(_as_int(row.get("tool_errors"), default=0)) for row in rows]),
        "fingerprint_recurrence_before_mean": _mean(fp_before_values),
        "fingerprint_recurrence_after_mean": _mean(fp_after_values),
        "lesson_activations_total": sum(_as_int(row.get("lesson_activations"), default=0) for row in rows),
        "promoted_total": sum(_as_int(row.get("promoted_count"), default=0) for row in rows),
        "suppressed_total": sum(_as_int(row.get("suppressed_count"), default=0) for row in rows),
        "retrieval_helped_total": retrieval_helped_total,
        "retrieval_activations_total": retrieval_total_total,
        "retrieval_help_ratio_weighted": retrieval_help_ratio_weighted,
        "elapsed_s_total": sum(_as_float(row.get("elapsed_s"), default=0.0) for row in rows),
    }


def _delta(after: float | None, before: float | None) -> float | None:
    if after is None or before is None:
        return None
    return after - before


def _clear_lessons() -> None:
    LESSONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    LESSONS_PATH.write_text("", encoding="utf-8")
    LESSONS_V2_PATH.parent.mkdir(parents=True, exist_ok=True)
    LESSONS_V2_PATH.write_text("", encoding="utf-8")
    MEMORY_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_EVENTS_PATH.write_text("", encoding="utf-8")


def _clear_escalation() -> None:
    if ESCALATION_STATE_PATH.exists():
        ESCALATION_STATE_PATH.unlink()


def _format_ratio(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def _format_optional(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def _run_phase(
    *,
    cfg: Any,
    phase: str,
    domain: str,
    task_id: str,
    n_runs: int,
    start_session: int,
    max_steps: int,
    learning_mode: str,
    model_executor: str,
    model_critic: str,
    model_judge: str | None,
    posttask_mode: str,
    bootstrap: bool,
    cryptic_errors: bool,
    semi_helpful_errors: bool,
    mixed_errors: bool,
    posttask_learn: bool,
    memory_v2_demo_mode: bool,
    verbose: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx in range(n_runs):
        run_idx = idx + 1
        session_id = start_session + idx
        print(
            f"  [{phase}] run {run_idx}/{n_runs} "
            f"session={session_id} domain={domain} task={task_id}"
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
            memory_v2_demo_mode=memory_v2_demo_mode,
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
        )
        elapsed_s = time.time() - t0
        row = _extract_row(
            phase=phase,
            domain=domain,
            task_id=task_id,
            run_idx=run_idx,
            session_id=session_id,
            elapsed_s=elapsed_s,
            metrics=result.metrics if isinstance(result.metrics, dict) else {},
        )
        rows.append(row)
        status = "PASS" if row["passed"] else "FAIL"
        print(
            f"    [{status}] score={row['score']:.2f} steps={row['steps']} "
            f"errors={row['tool_errors']} "
            f"fp_before={_format_optional(row['fingerprint_recurrence_before'])} "
            f"fp_after={_format_optional(row['fingerprint_recurrence_after'])} "
            f"activations={row['lesson_activations']} "
            f"promoted={row['promoted_count']} suppressed={row['suppressed_count']} "
            f"retrieval_help={_format_ratio(row['retrieval_help_ratio'])} "
            f"({row['elapsed_s']:.2f}s)"
        )
    return rows


def _phase_name_for_print(phase: str) -> str:
    if phase == "gridtool_warmup":
        return "GRIDTOOL WARMUP"
    if phase == "fluxtool_interference":
        return "FLUXTOOL INTERFERENCE"
    if phase == "gridtool_retention":
        return "GRIDTOOL RETENTION"
    return phase.upper()


def main() -> int:
    ap = argparse.ArgumentParser(description="Run Memory V2 stability benchmark")
    ap.add_argument("--grid-task-id", default="aggregate_report")
    ap.add_argument("--fluxtool-task-id", default="aggregate_report_holdout")
    ap.add_argument("--retention-task-id", default="")
    ap.add_argument("--grid-runs", type=int, default=3)
    ap.add_argument("--fluxtool-runs", type=int, default=3)
    ap.add_argument("--retention-runs", type=int, default=3)
    ap.add_argument("--start-session", type=int, default=15001)
    ap.add_argument("--max-steps", type=int, default=8)
    ap.add_argument("--learning-mode", default=DEFAULT_LEARNING_MODE, choices=LEARNING_MODES)
    ap.add_argument("--bootstrap", action="store_true")
    ap.add_argument("--cryptic-errors", action="store_true")
    ap.add_argument("--semi-helpful-errors", action="store_true")
    ap.add_argument("--mixed-errors", action="store_true")
    ap.add_argument("--model-executor", default=DEFAULT_EXECUTOR_MODEL)
    ap.add_argument("--model-critic", default=DEFAULT_CRITIC_MODEL)
    ap.add_argument("--model-judge", default=None)
    ap.add_argument("--posttask-mode", choices=["candidate", "direct"], default="direct")
    ap.add_argument("--no-posttask-learn", action="store_true")
    ap.add_argument(
        "--memory-v2-demo-mode",
        action="store_true",
        help="Suppress legacy posttask_hook/promotion_gate skill patching while keeping Memory V2 active",
    )
    ap.add_argument("--clear-lessons", action="store_true")
    ap.add_argument("--output-json", default="", help="Optional path to write JSON summary")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    _clear_escalation()
    if args.clear_lessons:
        _clear_lessons()

    retention_task_id = args.retention_task_id.strip() or args.grid_task_id
    model_executor = args.model_executor.strip() or DEFAULT_EXECUTOR_MODEL
    model_critic = args.model_critic.strip() or DEFAULT_CRITIC_MODEL
    model_judge = args.model_judge.strip() if args.model_judge else None
    posttask_learn = not args.no_posttask_learn

    print(f"\n{'=' * 78}")
    print("  Memory V2 Stability Benchmark")
    print(
        "  protocol=gridtool_warmup -> fluxtool_interference -> gridtool_retention"
    )
    print(
        f"  learning_mode={args.learning_mode} bootstrap={args.bootstrap} max_steps={args.max_steps} "
        f"posttask_mode={args.posttask_mode} posttask_learn={posttask_learn} "
        f"memory_v2_demo_mode={bool(args.memory_v2_demo_mode)}"
    )
    print(
        f"  runs: grid={args.grid_runs} flux={args.fluxtool_runs} retention={args.retention_runs} "
        f"start_session={args.start_session}"
    )
    print(f"{'=' * 78}\n")

    session_cursor = args.start_session
    rows: list[dict[str, Any]] = []

    phase_specs = [
        ("gridtool_warmup", "gridtool", args.grid_task_id, max(0, args.grid_runs)),
        ("fluxtool_interference", "fluxtool", args.fluxtool_task_id, max(0, args.fluxtool_runs)),
        ("gridtool_retention", "gridtool", retention_task_id, max(0, args.retention_runs)),
    ]

    for phase, domain, task_id, n_runs in phase_specs:
        print(f"--- {_phase_name_for_print(phase)} ({n_runs} runs) ---")
        phase_rows = _run_phase(
            cfg=cfg,
            phase=phase,
            domain=domain,
            task_id=task_id,
            n_runs=n_runs,
            start_session=session_cursor,
            max_steps=args.max_steps,
            learning_mode=args.learning_mode,
            model_executor=model_executor,
            model_critic=model_critic,
            model_judge=model_judge,
            posttask_mode=args.posttask_mode,
            bootstrap=args.bootstrap,
            cryptic_errors=args.cryptic_errors,
            semi_helpful_errors=args.semi_helpful_errors,
            mixed_errors=args.mixed_errors,
            posttask_learn=posttask_learn,
            memory_v2_demo_mode=bool(args.memory_v2_demo_mode),
            verbose=args.verbose,
        )
        rows.extend(phase_rows)
        session_cursor += n_runs
        print()

    phase_summary: dict[str, dict[str, Any]] = {}
    for phase, _, _, _ in phase_specs:
        phase_rows = [row for row in rows if row.get("phase") == phase]
        phase_summary[phase] = _aggregate_rows(phase_rows)

    overall_summary = _aggregate_rows(rows)

    warmup = phase_summary.get("gridtool_warmup", {})
    retention = phase_summary.get("gridtool_retention", {})
    retention_delta = {
        "pass_rate_delta": _delta(
            retention.get("pass_rate") if isinstance(retention.get("pass_rate"), (int, float)) else None,
            warmup.get("pass_rate") if isinstance(warmup.get("pass_rate"), (int, float)) else None,
        ),
        "mean_score_delta": _delta(
            retention.get("mean_score") if isinstance(retention.get("mean_score"), (int, float)) else None,
            warmup.get("mean_score") if isinstance(warmup.get("mean_score"), (int, float)) else None,
        ),
        "mean_steps_delta": _delta(
            retention.get("mean_steps") if isinstance(retention.get("mean_steps"), (int, float)) else None,
            warmup.get("mean_steps") if isinstance(warmup.get("mean_steps"), (int, float)) else None,
        ),
        "mean_tool_errors_delta": _delta(
            retention.get("mean_tool_errors") if isinstance(retention.get("mean_tool_errors"), (int, float)) else None,
            warmup.get("mean_tool_errors") if isinstance(warmup.get("mean_tool_errors"), (int, float)) else None,
        ),
        "fingerprint_recurrence_after_delta": _delta(
            retention.get("fingerprint_recurrence_after_mean")
            if isinstance(retention.get("fingerprint_recurrence_after_mean"), (int, float))
            else None,
            warmup.get("fingerprint_recurrence_after_mean")
            if isinstance(warmup.get("fingerprint_recurrence_after_mean"), (int, float))
            else None,
        ),
    }

    print(f"{'=' * 78}")
    print("  Run Table")
    print(f"{'=' * 78}")
    print(
        f"{'Phase':<24} {'Run':>3} {'Session':>8} {'Pass':>5} {'Score':>6} {'Steps':>6} "
        f"{'Errs':>5} {'FP_B':>6} {'FP_A':>6} {'Acts':>5} {'Promo':>5} {'Supp':>4} {'RH':>5}"
    )
    for row in rows:
        print(
            f"{row['phase']:<24} {row['run']:>3} {row['session_id']:>8} "
            f"{('Y' if row['passed'] else 'N'):>5} {row['score']:>6.2f} {row['steps']:>6} "
            f"{row['tool_errors']:>5} {_format_optional(row['fingerprint_recurrence_before']):>6} "
            f"{_format_optional(row['fingerprint_recurrence_after']):>6} {row['lesson_activations']:>5} "
            f"{row['promoted_count']:>5} {row['suppressed_count']:>4} {_format_ratio(row['retrieval_help_ratio']):>5}"
        )

    print(f"\n{'=' * 78}")
    print("  Phase Summary")
    print(f"{'=' * 78}")
    print(
        f"{'Phase':<24} {'PassRate':>8} {'Score':>7} {'Steps':>7} {'Errs':>7} "
        f"{'FP_B':>7} {'FP_A':>7} {'Acts':>6} {'Promo':>6} {'Supp':>5} {'RH':>6}"
    )
    for phase, summary in phase_summary.items():
        pass_rate = _as_float(summary.get("pass_rate"), default=0.0)
        print(
            f"{phase:<24} {pass_rate:>8.2%} {_format_optional(summary.get('mean_score')):>7} "
            f"{_format_optional(summary.get('mean_steps')):>7} {_format_optional(summary.get('mean_tool_errors')):>7} "
            f"{_format_optional(summary.get('fingerprint_recurrence_before_mean')):>7} "
            f"{_format_optional(summary.get('fingerprint_recurrence_after_mean')):>7} "
            f"{_as_int(summary.get('lesson_activations_total'), default=0):>6} "
            f"{_as_int(summary.get('promoted_total'), default=0):>6} "
            f"{_as_int(summary.get('suppressed_total'), default=0):>5} "
            f"{_format_ratio(summary.get('retrieval_help_ratio_weighted')):>6}"
        )

    payload: dict[str, Any] = {
        "config": {
            "grid_task_id": args.grid_task_id,
            "fluxtool_task_id": args.fluxtool_task_id,
            "retention_task_id": retention_task_id,
            "grid_runs": args.grid_runs,
            "fluxtool_runs": args.fluxtool_runs,
            "retention_runs": args.retention_runs,
            "start_session": args.start_session,
            "max_steps": args.max_steps,
            "learning_mode": args.learning_mode,
            "bootstrap": args.bootstrap,
            "cryptic_errors": args.cryptic_errors,
            "semi_helpful_errors": args.semi_helpful_errors,
            "mixed_errors": args.mixed_errors,
            "posttask_mode": args.posttask_mode,
            "posttask_learn": posttask_learn,
            "memory_v2_demo_mode": bool(args.memory_v2_demo_mode),
            "model_executor": model_executor,
            "model_critic": model_critic,
            "model_judge": model_judge,
            "clear_lessons": args.clear_lessons,
        },
        "protocol": ["gridtool_warmup", "fluxtool_interference", "gridtool_retention"],
        "phase_summary": phase_summary,
        "overall_summary": overall_summary,
        "retention_delta": retention_delta,
        "runs": rows,
    }

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        print(f"\nWrote JSON summary: {output_path}")

    print("\nJSON summary:")
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
