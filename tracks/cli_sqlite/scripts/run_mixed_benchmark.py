#!/usr/bin/env python3
"""Run the mixed Memory V2 benchmark protocol in one command.

Protocol order:
1) gridtool warmup
2) fluxtool interference
3) shell excel interference
4) sqlite interference
5) gridtool retention
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
DEFAULT_TRANSFER_RETRIEVAL_MAX_RESULTS = int(getattr(agent_cli, "DEFAULT_TRANSFER_RETRIEVAL_MAX_RESULTS", 0))
DEFAULT_TRANSFER_RETRIEVAL_SCORE_WEIGHT = float(getattr(agent_cli, "DEFAULT_TRANSFER_RETRIEVAL_SCORE_WEIGHT", 0.0))
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


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / float(len(values))


def _first_present(mapping: dict[str, Any], keys: list[str]) -> Any | None:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


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
    return {
        "phase": phase,
        "domain": domain,
        "task_id": task_id,
        "run": run_idx,
        "session_id": session_id,
        "passed": bool(_first_present(metrics, ["eval_passed", "passed", "judge_passed"]) or False),
        "score": _as_float(_first_present(metrics, ["eval_score", "score", "judge_score"]), default=0.0),
        "steps": _as_int(_first_present(metrics, ["steps"]), default=0),
        "tool_errors": _as_int(_first_present(metrics, ["tool_errors", "errors"]), default=0),
        "lessons_loaded": _as_int(_first_present(metrics, ["lessons_loaded", "v2_lessons_loaded"]), default=0),
        "lessons_generated": _as_int(_first_present(metrics, ["lessons_generated", "v2_lessons_generated"]), default=0),
        "lesson_activations": _as_int(_first_present(metrics, ["lesson_activations", "v2_lesson_activations"]), default=0),
        "elapsed_s": round(elapsed_s, 2),
    }


def _aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    runs = len(rows)
    if runs == 0:
        return {
            "runs": 0,
            "pass_count": 0,
            "fail_count": 0,
            "pass_rate": 0.0,
            "mean_score": None,
            "mean_steps": None,
            "mean_tool_errors": None,
            "lesson_activations_total": 0,
            "elapsed_s_total": 0.0,
        }

    pass_count = sum(1 for row in rows if bool(row.get("passed", False)))
    return {
        "runs": runs,
        "pass_count": pass_count,
        "fail_count": runs - pass_count,
        "pass_rate": pass_count / float(runs),
        "mean_score": _mean([_as_float(row.get("score"), default=0.0) for row in rows]),
        "mean_steps": _mean([float(_as_int(row.get("steps"), default=0)) for row in rows]),
        "mean_tool_errors": _mean([float(_as_int(row.get("tool_errors"), default=0)) for row in rows]),
        "lesson_activations_total": sum(_as_int(row.get("lesson_activations"), default=0) for row in rows),
        "elapsed_s_total": sum(_as_float(row.get("elapsed_s"), default=0.0) for row in rows),
    }


def _delta(after: float | None, before: float | None) -> float | None:
    if after is None or before is None:
        return None
    return after - before


def _format_optional(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def _phase_name_for_print(phase: str) -> str:
    if phase == "grid_warmup":
        return "GRID WARMUP"
    if phase == "fluxtool_interference":
        return "FLUXTOOL INTERFERENCE"
    if phase == "shell_excel_interference":
        return "SHELL-EXCEL INTERFERENCE"
    if phase == "sqlite_interference":
        return "SQLITE INTERFERENCE"
    if phase == "grid_retention":
        return "GRID RETENTION"
    return phase.upper()


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
    posttask_learn: bool,
    memory_v2_demo_mode: bool,
    bootstrap: bool,
    cryptic_errors: bool,
    semi_helpful_errors: bool,
    mixed_errors: bool,
    enable_transfer_retrieval: bool,
    transfer_retrieval_max_results: int,
    transfer_retrieval_score_weight: float,
    verbose: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx in range(n_runs):
        run_idx = idx + 1
        session_id = start_session + idx
        print(f"  [{phase}] run {run_idx}/{n_runs} session={session_id} domain={domain} task={task_id}")
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
            enable_transfer_retrieval=enable_transfer_retrieval,
            transfer_retrieval_max_results=max(0, int(transfer_retrieval_max_results)),
            transfer_retrieval_score_weight=max(0.0, float(transfer_retrieval_score_weight)),
        )
        row = _extract_row(
            phase=phase,
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
            f"    [{status}] score={row['score']:.2f} steps={row['steps']} errors={row['tool_errors']} "
            f"lessons_in={row['lessons_loaded']} lessons_out={row['lessons_generated']} "
            f"acts={row['lesson_activations']} ({row['elapsed_s']:.2f}s)"
        )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Run mixed grid->fluxtool->shell(excel)->sqlite->grid retention benchmark")
    ap.add_argument("--grid-task-id", default="aggregate_report")
    ap.add_argument("--fluxtool-task-id", default="aggregate_report_holdout")
    ap.add_argument("--shell-task-id", default="shell_excel_build_report")
    ap.add_argument("--sqlite-task-id", default="import_aggregate")
    ap.add_argument("--retention-task-id", default="")
    ap.add_argument("--grid-runs", type=int, default=1)
    ap.add_argument("--fluxtool-runs", type=int, default=1)
    ap.add_argument("--shell-runs", type=int, default=1)
    ap.add_argument("--sqlite-runs", type=int, default=1)
    ap.add_argument("--retention-runs", type=int, default=1)
    ap.add_argument("--start-session", type=int, default=52001)
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
    ap.add_argument(
        "--enable-transfer-retrieval",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable cross-domain transfer lane for on-error Memory V2 retrieval",
    )
    ap.add_argument(
        "--transfer-retrieval-max-results",
        type=int,
        default=DEFAULT_TRANSFER_RETRIEVAL_MAX_RESULTS,
        help="Maximum transfer-lane hints per failed step",
    )
    ap.add_argument(
        "--transfer-retrieval-score-weight",
        type=float,
        default=DEFAULT_TRANSFER_RETRIEVAL_SCORE_WEIGHT,
        help="Score multiplier applied to transfer-lane candidates",
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

    phase_specs: list[tuple[str, str, str, int]] = [
        ("grid_warmup", "gridtool", args.grid_task_id, max(0, int(args.grid_runs))),
        ("fluxtool_interference", "fluxtool", args.fluxtool_task_id, max(0, int(args.fluxtool_runs))),
        ("shell_excel_interference", "shell", args.shell_task_id, max(0, int(args.shell_runs))),
        ("sqlite_interference", "sqlite", args.sqlite_task_id, max(0, int(args.sqlite_runs))),
        ("grid_retention", "gridtool", retention_task_id, max(0, int(args.retention_runs))),
    ]

    print(f"\n{'=' * 92}")
    print("  Mixed Memory Benchmark")
    print("  protocol=gridtool -> fluxtool -> shell(excel) -> sqlite -> gridtool(retention)")
    print(
        f"  learning_mode={args.learning_mode} bootstrap={args.bootstrap} max_steps={args.max_steps} "
        f"posttask_mode={args.posttask_mode} posttask_learn={posttask_learn} "
        f"transfer_retrieval={bool(args.enable_transfer_retrieval)}"
    )
    print(
        f"  runs: grid={args.grid_runs} flux={args.fluxtool_runs} shell={args.shell_runs} "
        f"sqlite={args.sqlite_runs} retention={args.retention_runs} start_session={args.start_session}"
    )
    print(f"{'=' * 92}\n")

    session_cursor = args.start_session
    rows: list[dict[str, Any]] = []

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
            posttask_learn=posttask_learn,
            memory_v2_demo_mode=bool(args.memory_v2_demo_mode),
            bootstrap=args.bootstrap,
            cryptic_errors=args.cryptic_errors,
            semi_helpful_errors=args.semi_helpful_errors,
            mixed_errors=args.mixed_errors,
            enable_transfer_retrieval=bool(args.enable_transfer_retrieval),
            transfer_retrieval_max_results=max(0, int(args.transfer_retrieval_max_results)),
            transfer_retrieval_score_weight=max(0.0, float(args.transfer_retrieval_score_weight)),
            verbose=args.verbose,
        )
        rows.extend(phase_rows)
        session_cursor += n_runs
        print()

    phase_summary: dict[str, dict[str, Any]] = {}
    for phase, _, _, _ in phase_specs:
        phase_summary[phase] = _aggregate_rows([row for row in rows if row.get("phase") == phase])
    overall_summary = _aggregate_rows(rows)

    warmup = phase_summary.get("grid_warmup", {})
    retention = phase_summary.get("grid_retention", {})
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
    }

    print(f"{'=' * 92}")
    print("  Run Table")
    print(f"{'=' * 92}")
    print(
        f"{'Phase':<25} {'Run':>3} {'Session':>8} {'Pass':>5} {'Score':>6} {'Steps':>5} "
        f"{'Errs':>5} {'In':>4} {'Out':>4} {'Acts':>5} {'Time':>7}"
    )
    for row in rows:
        print(
            f"{row['phase']:<25} {row['run']:>3} {row['session_id']:>8} "
            f"{('Y' if row['passed'] else 'N'):>5} {row['score']:>6.2f} {row['steps']:>5} "
            f"{row['tool_errors']:>5} {row['lessons_loaded']:>4} {row['lessons_generated']:>4} "
            f"{row['lesson_activations']:>5} {row['elapsed_s']:>6.2f}s"
        )

    print(f"\n{'=' * 92}")
    print("  Phase Summary")
    print(f"{'=' * 92}")
    print(f"{'Phase':<25} {'PassRate':>8} {'Score':>7} {'Steps':>7} {'Errs':>7} {'Acts':>6} {'Time':>8}")
    for phase, summary in phase_summary.items():
        pass_rate = _as_float(summary.get("pass_rate"), default=0.0)
        print(
            f"{phase:<25} {pass_rate:>8.2%} {_format_optional(summary.get('mean_score')):>7} "
            f"{_format_optional(summary.get('mean_steps')):>7} {_format_optional(summary.get('mean_tool_errors')):>7} "
            f"{_as_int(summary.get('lesson_activations_total'), default=0):>6} "
            f"{_as_float(summary.get('elapsed_s_total'), default=0.0):>7.2f}s"
        )

    payload: dict[str, Any] = {
        "config": {
            "grid_task_id": args.grid_task_id,
            "fluxtool_task_id": args.fluxtool_task_id,
            "shell_task_id": args.shell_task_id,
            "sqlite_task_id": args.sqlite_task_id,
            "retention_task_id": retention_task_id,
            "grid_runs": args.grid_runs,
            "fluxtool_runs": args.fluxtool_runs,
            "shell_runs": args.shell_runs,
            "sqlite_runs": args.sqlite_runs,
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
            "enable_transfer_retrieval": bool(args.enable_transfer_retrieval),
            "transfer_retrieval_max_results": max(0, int(args.transfer_retrieval_max_results)),
            "transfer_retrieval_score_weight": max(0.0, float(args.transfer_retrieval_score_weight)),
            "model_executor": model_executor,
            "model_critic": model_critic,
            "model_judge": model_judge,
            "clear_lessons": args.clear_lessons,
        },
        "protocol": [
            {"phase": phase, "domain": domain, "task_id": task_id, "runs": n_runs}
            for phase, domain, task_id, n_runs in phase_specs
        ],
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
