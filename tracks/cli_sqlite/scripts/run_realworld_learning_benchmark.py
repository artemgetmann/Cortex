#!/usr/bin/env python3
"""Run real-world CLI learning benchmark with docs + persistence ablations."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from statistics import median
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from config import load_config
from tracks.cli_sqlite import agent_cli


TRACK_ROOT = Path(__file__).resolve().parents[1]
LEARNING_ROOT = TRACK_ROOT / "learning"
REPORTS_ROOT = TRACK_ROOT / "reports"

DEFAULT_LESSONS_PATH = LEARNING_ROOT / "lessons.jsonl"
DEFAULT_LESSONS_V2_PATH = LEARNING_ROOT / "lessons_v2.jsonl"
DEFAULT_MEMORY_EVENTS_PATH = LEARNING_ROOT / "memory_events.jsonl"
DEFAULT_ESCALATION_PATH = LEARNING_ROOT / "critic_escalation_state.json"

DEFAULT_LEARNING_MODE = str(getattr(agent_cli, "DEFAULT_LEARNING_MODE", "strict"))
LEARNING_MODES = tuple(getattr(agent_cli, "LEARNING_MODES", ("legacy", "strict")))
BENCHMARK_DEFAULT_LEARNING_MODE = "strict" if "strict" in LEARNING_MODES else DEFAULT_LEARNING_MODE
DEFAULT_EXECUTOR_MODEL = str(getattr(agent_cli, "DEFAULT_EXECUTOR_MODEL", "claude-haiku-4-5"))
DEFAULT_BENCHMARK_DETERMINISTIC = bool(getattr(agent_cli, "DEFAULT_BENCHMARK_DETERMINISTIC", False))
DEFAULT_BENCHMARK_PROMOTED_ONLY = bool(getattr(agent_cli, "DEFAULT_BENCHMARK_PROMOTED_ONLY", False))

run_cli_agent = agent_cli.run_cli_agent
LESSONS_PATH = Path(getattr(agent_cli, "LESSONS_PATH", DEFAULT_LESSONS_PATH))
LESSONS_V2_PATH = Path(getattr(agent_cli, "LESSONS_V2_PATH", DEFAULT_LESSONS_V2_PATH))
MEMORY_EVENTS_PATH = Path(getattr(agent_cli, "MEMORY_EVENTS_PATH", DEFAULT_MEMORY_EVENTS_PATH))
ESCALATION_STATE_PATH = Path(getattr(agent_cli, "ESCALATION_STATE_PATH", DEFAULT_ESCALATION_PATH))

# Each domain has explicit train and transfer tasks with deterministic CONTRACT checks.
DOMAIN_SUITES: tuple[dict[str, Any], ...] = (
    {
        "suite": "git",
        "train": {"domain": "shell", "task_id": "shell_git_train_release_flow"},
        "transfer": {"domain": "shell", "task_id": "shell_git_transfer_hotfix"},
        "docs": ["tracks/cli_sqlite/domains/docs/shell-git-reference.md"],
    },
    {
        "suite": "sqlite",
        "train": {"domain": "sqlite", "task_id": "import_aggregate"},
        "transfer": {"domain": "sqlite", "task_id": "incremental_reconcile"},
        "docs": ["tracks/cli_sqlite/domains/docs/sqlite-reference.md"],
    },
    {
        "suite": "xlsx",
        "train": {"domain": "shell", "task_id": "shell_excel_build_report"},
        "transfer": {"domain": "shell", "task_id": "shell_excel_multi_summary"},
        "docs": ["tracks/cli_sqlite/domains/docs/shell-xlsx-reference.md"],
    },
)


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


def _clear_learning_state() -> None:
    # Arms and lessons-off runs need hard isolation to avoid contamination.
    for path in (LESSONS_PATH, LESSONS_V2_PATH, MEMORY_EVENTS_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    if ESCALATION_STATE_PATH.exists():
        ESCALATION_STATE_PATH.unlink()


def _build_ablations() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for docs_enabled in (False, True):
        for doc_mode in ("lossy", "full"):
            for lessons_enabled in (False, True):
                rows.append(
                    {
                        "arm_id": (
                            f"docs_{'on' if docs_enabled else 'off'}"
                            f"__mode_{doc_mode}"
                            f"__lessons_{'on' if lessons_enabled else 'off'}"
                        ),
                        "docs_enabled": docs_enabled,
                        "doc_mode": doc_mode,
                        "lessons_enabled": lessons_enabled,
                    }
                )
    return rows


def _build_task_schedule() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for suite in DOMAIN_SUITES:
        rows.append(
            {
                "suite": str(suite["suite"]),
                "phase": "train",
                "domain": str(suite["train"]["domain"]),
                "task_id": str(suite["train"]["task_id"]),
            }
        )
        rows.append(
            {
                "suite": str(suite["suite"]),
                "phase": "transfer",
                "domain": str(suite["transfer"]["domain"]),
                "task_id": str(suite["transfer"]["task_id"]),
            }
        )
    return rows


def _pick_task_for_run(run_index: int, schedule: list[dict[str, str]]) -> dict[str, str]:
    idx = (run_index - 1) % len(schedule)
    return schedule[idx]


def _median_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return float(median(values))


def _success_rate_by_session(rows: list[dict[str, Any]]) -> dict[str, float]:
    by_run: dict[int, list[int]] = {}
    for row in rows:
        run_idx = _as_int(row.get("run_index", 0), default=0)
        by_run.setdefault(run_idx, []).append(1 if bool(row.get("passed", False)) else 0)
    out: dict[str, float] = {}
    for run_idx in sorted(by_run):
        values = by_run[run_idx]
        out[str(run_idx)] = (sum(values) / float(len(values))) if values else 0.0
    return out


def _build_row(
    *,
    arm: dict[str, Any],
    run_index: int,
    session_id: int,
    elapsed_s: float,
    task_spec: dict[str, str],
    effective_doc_mode: str,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    recurrence_before = _as_float(metrics.get("v2_fingerprint_recurrence_before", 0.0), default=0.0)
    recurrence_after = _as_float(metrics.get("v2_fingerprint_recurrence_after", 0.0), default=0.0)
    repeated_signatures = metrics.get("repeated_error_signatures", [])
    repeated_signature_count = len(repeated_signatures) if isinstance(repeated_signatures, list) else 0
    lesson_activations = _as_int(
        metrics.get("v2_lesson_activations", metrics.get("lesson_activations", 0)),
        default=0,
    )
    step_activations_raw = metrics.get("v2_lesson_activations_by_step", {})
    step_activations: dict[str, int] = {}
    if isinstance(step_activations_raw, dict):
        for key, value in step_activations_raw.items():
            step_key = str(key).strip()
            if not step_key:
                continue
            step_activations[step_key] = _as_int(value, default=0)
    return {
        "arm_id": str(arm["arm_id"]),
        "docs_enabled": bool(arm["docs_enabled"]),
        "doc_mode": str(effective_doc_mode),
        "lessons_enabled": bool(arm["lessons_enabled"]),
        "run_index": int(run_index),
        "session_id": int(session_id),
        "suite": str(task_spec["suite"]),
        "phase": str(task_spec["phase"]),
        "domain": str(task_spec["domain"]),
        "task_id": str(task_spec["task_id"]),
        "passed": bool(metrics.get("eval_passed", False)),
        "score": _as_float(metrics.get("eval_score", 0.0), default=0.0),
        "steps": _as_int(metrics.get("steps", 0), default=0),
        "tool_errors": _as_int(metrics.get("tool_errors", 0), default=0),
        "lessons_loaded": _as_int(metrics.get("lessons_loaded", 0), default=0),
        "lessons_generated": _as_int(metrics.get("lessons_generated", 0), default=0),
        "lesson_activations": lesson_activations,
        "lesson_activations_by_step": step_activations,
        "promoted_count": _as_int(metrics.get("v2_promoted", 0), default=0),
        "suppressed_count": _as_int(metrics.get("v2_suppressed", 0), default=0),
        "retrieval_help_ratio": _as_float(metrics.get("v2_retrieval_help_ratio", 0.0), default=0.0),
        "judge_invoked": bool(metrics.get("judge_invoked", False)),
        "transfer_retrieval_enabled": bool(metrics.get("v2_transfer_retrieval_enabled", False)),
        "transfer_lane_activations": _as_int(metrics.get("v2_transfer_lane_activations", 0), default=0),
        "prerun_lesson_ids": list(metrics.get("v2_prerun_lesson_ids", []))
        if isinstance(metrics.get("v2_prerun_lesson_ids", []), list)
        else [],
        "repeated_signature_count": repeated_signature_count,
        "recurrence_before": recurrence_before,
        "recurrence_after": recurrence_after,
        "fingerprint_recurrence_before": recurrence_before,
        "fingerprint_recurrence_after": recurrence_after,
        "repeated_error_delta": recurrence_after - recurrence_before,
        "elapsed_s": round(elapsed_s, 3),
    }


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "run_count": 0,
            "pass_rate": 0.0,
            "success_rate_by_session": {},
            "median_steps_to_success": None,
            "median_repeated_error_delta": None,
            "mean_lesson_activations": 0.0,
            "mean_retrieval_help_ratio": 0.0,
            "mean_lesson_activations_by_step": {},
            "activation_nonzero_run_count": 0,
        }
    pass_count = sum(1 for row in rows if bool(row.get("passed", False)))
    success_steps = [_as_float(row.get("steps", 0), default=0.0) for row in rows if bool(row.get("passed", False))]
    repeated_deltas = [_as_float(row.get("repeated_error_delta", 0.0), default=0.0) for row in rows]
    lesson_activations = [_as_float(row.get("lesson_activations", 0.0), default=0.0) for row in rows]
    retrieval_ratios = [_as_float(row.get("retrieval_help_ratio", 0.0), default=0.0) for row in rows]
    mean_activations = (sum(lesson_activations) / float(len(lesson_activations))) if lesson_activations else 0.0
    mean_retrieval = (sum(retrieval_ratios) / float(len(retrieval_ratios))) if retrieval_ratios else 0.0
    step_totals: dict[str, float] = {}
    activation_nonzero_run_count = 0
    for row in rows:
        raw = row.get("lesson_activations_by_step", {})
        if not isinstance(raw, dict):
            continue
        run_total = 0
        for key, value in raw.items():
            step_key = str(key).strip()
            if not step_key:
                continue
            amount = _as_float(value, default=0.0)
            if amount != 0.0:
                run_total += 1
            step_totals[step_key] = step_totals.get(step_key, 0.0) + amount
        if run_total > 0:
            activation_nonzero_run_count += 1
    divisor = float(len(rows)) if rows else 1.0
    mean_step_profile = {
        key: round(step_totals.get(key, 0.0) / divisor, 4)
        for key in sorted(step_totals, key=lambda item: int(item) if str(item).isdigit() else str(item))
    }
    return {
        "run_count": len(rows),
        "pass_rate": pass_count / float(len(rows)),
        "success_rate_by_session": _success_rate_by_session(rows),
        "median_steps_to_success": _median_or_none(success_steps),
        "median_repeated_error_delta": _median_or_none(repeated_deltas),
        "mean_lesson_activations": round(mean_activations, 4),
        "mean_retrieval_help_ratio": round(mean_retrieval, 4),
        "mean_lesson_activations_by_step": mean_step_profile,
        "activation_nonzero_run_count": int(activation_nonzero_run_count),
    }


def _transfer_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    transfer_rows = [row for row in rows if str(row.get("phase", "")) == "transfer"]
    per_suite: dict[str, dict[str, Any]] = {}
    for suite in sorted({str(row.get("suite", "")) for row in transfer_rows}):
        suite_rows = [row for row in transfer_rows if str(row.get("suite", "")) == suite]
        per_suite[suite] = _summarize(suite_rows)
    return {
        **_summarize(transfer_rows),
        "by_suite": per_suite,
    }


def _format_optional(value: float | None, precision: int = 3) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.{precision}f}"


def _render_markdown(payload: dict[str, Any]) -> str:
    overall = payload["overall"]
    learning_gate = _learning_gate(payload.get("runs", []))
    lines = [
        "# Real-World CLI Learning Benchmark",
        "",
        "## Metric Glossary",
        "",
        "- `pass_rate`: fraction of runs that passed deterministic contract checks. High = reliable execution; low = unstable execution.",
        "- `transfer_pass_rate`: pass rate on transfer-phase runs only (unseen/harder tasks). High = better generalization; low = overfitting to train tasks.",
        "- `mean_X`: arithmetic average of metric X across selected runs. High/low depends on metric semantics, but it smooths run-to-run noise.",
        "- `median_X`: middle value of metric X across selected runs. High/low depends on metric semantics; more robust than mean against outliers.",
        "- `median_steps_to_success`: median step count among successful runs only. Low = faster convergence; high = slower/less efficient.",
        "- `repeated_error_delta`: `fingerprint_recurrence_after - fingerprint_recurrence_before` within a run. Negative = fewer repeated mistakes; positive = more repeated mistakes.",
        "- `median_repeated_error_delta`: median of `repeated_error_delta` across runs. Negative is good; positive is bad.",
        "- `transfer_pass_delta`: `last_transfer_pass - first_transfer_pass` over run index. Positive = transfer pass trend improved.",
        "- `activation_delta`: `last_transfer_lesson_activations - first_transfer_lesson_activations`. Positive = lesson mechanism engaged more over time.",
        "- `retrieval_help_ratio_delta`: `last_transfer_retrieval_help_ratio - first_transfer_retrieval_help_ratio`. Positive = retrieved lessons helped more over time.",
        "",
        "## How To Read This Report",
        "",
        "- Primary signal: `transfer_pass_rate` and `transfer_pass_delta`.",
        "- Mechanism signal: `activation_delta` and `retrieval_help_ratio_delta` should be positive, not just pass/fail changes.",
        "- Error hygiene signal: `median_repeated_error_delta` should move negative over stronger runs.",
        "- Gate: claim learning only when transfer improves and mechanism signals are non-zero/positive.",
        "",
        "## Conclusion",
        "",
        f"- did_learning_improve: `{payload['did_learning_improve']}`",
        (
            "- learning_gate: "
            f"`transfer_pass_lift={learning_gate['transfer_pass_lift']}, "
            f"activation_nonzero={learning_gate['activation_nonzero']}, "
            f"activation_trend={learning_gate['activation_trend']}, "
            f"retrieval_help_ratio_lift={learning_gate['retrieval_help_ratio_lift']}`"
        ),
        f"- transfer_pass_delta: `{learning_gate['transfer_pass_delta']:.4f}`",
        f"- activation_delta: `{learning_gate['activation_delta']:.4f}`",
        f"- retrieval_help_ratio_delta: `{learning_gate['retrieval_help_ratio_delta']:.4f}`",
        f"- success_rate_by_session: `{json.dumps(overall['success_rate_by_session'], sort_keys=True)}`",
        f"- median_steps_to_success: `{_format_optional(overall['median_steps_to_success'])}`",
        f"- median_repeated_error_delta: `{_format_optional(overall['median_repeated_error_delta'])}`",
        f"- mean_lesson_activations: `{_format_optional(overall['mean_lesson_activations'])}`",
        f"- mean_retrieval_help_ratio: `{_format_optional(overall['mean_retrieval_help_ratio'])}`",
        f"- mean_lesson_activations_by_step: `{json.dumps(overall.get('mean_lesson_activations_by_step', {}), sort_keys=True)}`",
        f"- activation_nonzero_run_count: `{int(overall.get('activation_nonzero_run_count', 0))}`",
        "",
        "## Transfer (Unseen Tasks)",
        "",
        f"- overall_transfer_pass_rate: `{float(payload['transfer']['pass_rate']):.2%}`",
        f"- overall_transfer_median_steps_to_success: `{_format_optional(payload['transfer']['median_steps_to_success'])}`",
        f"- overall_transfer_median_repeated_error_delta: `{_format_optional(payload['transfer']['median_repeated_error_delta'])}`",
        f"- overall_transfer_mean_lesson_activations: `{_format_optional(payload['transfer']['mean_lesson_activations'])}`",
        f"- overall_transfer_mean_retrieval_help_ratio: `{_format_optional(payload['transfer']['mean_retrieval_help_ratio'])}`",
        f"- overall_transfer_mean_lesson_activations_by_step: `{json.dumps(payload['transfer'].get('mean_lesson_activations_by_step', {}), sort_keys=True)}`",
        "",
        "## Arm Results",
        "",
        "| arm_id | docs | doc_mode | lessons | pass_rate | median_steps_to_success | median_repeated_error_delta | mean_lesson_activations | retrieval_help_ratio_delta | transfer_pass_rate |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for arm_id in sorted(payload["arms"]):
        arm = payload["arms"][arm_id]
        summary = arm["summary"]
        transfer = arm["transfer"]
        arm_gate = _learning_gate(arm.get("runs", []))
        lines.append(
            f"| {arm_id} | "
            f"{'on' if arm['docs_enabled'] else 'off'} | "
            f"{arm['doc_mode']} | "
            f"{'on' if arm['lessons_enabled'] else 'off'} | "
            f"{float(summary['pass_rate']):.2%} | "
            f"{_format_optional(summary['median_steps_to_success'])} | "
            f"{_format_optional(summary['median_repeated_error_delta'])} | "
            f"{_format_optional(summary['mean_lesson_activations'])} | "
            f"{float(arm_gate.get('retrieval_help_ratio_delta', 0.0)):.4f} | "
            f"{float(transfer['pass_rate']):.2%} |"
        )
    lines.extend(
        [
            "",
            "## Artifact Notes",
            "",
            "- `contract_gap_postretry.json`: deterministic final gap check after retry; unresolved rows are the exact blockers that still failed contract.",
            "- `target_repo/hotfix.txt` (git transfer tasks): verifies patch content actually landed in target repo.",
            "- `target_repo/transfer_summary.txt` (git transfer tasks): verifies expected transfer metadata (`TRANSFER_BRANCH`, `TRANSFER_PATCHES`) was produced.",
        ]
    )
    lines.append("")
    return "\n".join(lines)


def _infer_learning_gain(payload: dict[str, Any]) -> bool:
    gate = _learning_gate(payload.get("runs", []))
    return bool(gate.get("did_learning_improve", False))


def _mean_series_by_run(
    rows: list[dict[str, Any]],
    *,
    key: str,
    phase: str | None = None,
    bool_as_int: bool = False,
) -> list[float]:
    grouped: dict[int, list[float]] = {}
    for row in rows:
        if phase and str(row.get("phase", "")).strip().lower() != phase:
            continue
        run_idx = _as_int(row.get("run_index", 0), default=0)
        raw = row.get(key, 0)
        if bool_as_int:
            value = 1.0 if bool(raw) else 0.0
        else:
            value = _as_float(raw, default=0.0)
        grouped.setdefault(run_idx, []).append(value)
    ordered: list[float] = []
    for run_idx in sorted(grouped):
        values = grouped[run_idx]
        if not values:
            continue
        ordered.append(sum(values) / float(len(values)))
    return ordered


def _learning_gate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    # Learning is credited only when harder transfer outcomes improve and
    # mechanism signals show retrieval/activation actually engaged.
    transfer_pass_series = _mean_series_by_run(rows, key="passed", phase="transfer", bool_as_int=True)
    activation_series = _mean_series_by_run(rows, key="lesson_activations", phase="transfer")
    retrieval_series = _mean_series_by_run(rows, key="retrieval_help_ratio", phase="transfer")

    if (
        len(transfer_pass_series) < 2
        or len(activation_series) < 2
        or len(retrieval_series) < 2
    ):
        return {
            "did_learning_improve": False,
            "transfer_pass_lift": False,
            "activation_nonzero": False,
            "activation_trend": False,
            "retrieval_help_ratio_lift": False,
            "transfer_pass_delta": 0.0,
            "activation_delta": 0.0,
            "retrieval_help_ratio_delta": 0.0,
        }

    transfer_pass_delta = transfer_pass_series[-1] - transfer_pass_series[0]
    activation_delta = activation_series[-1] - activation_series[0]
    retrieval_help_ratio_delta = retrieval_series[-1] - retrieval_series[0]
    transfer_pass_lift = transfer_pass_series[-1] > transfer_pass_series[0]
    activation_nonzero = any(value > 0.0 for value in activation_series)
    activation_trend = activation_series[-1] >= activation_series[0]
    retrieval_help_ratio_lift = retrieval_series[-1] > retrieval_series[0]
    did_learning_improve = (
        transfer_pass_lift
        and activation_nonzero
        and activation_trend
        and retrieval_help_ratio_lift
    )
    return {
        "did_learning_improve": did_learning_improve,
        "transfer_pass_lift": transfer_pass_lift,
        "activation_nonzero": activation_nonzero,
        "activation_trend": activation_trend,
        "retrieval_help_ratio_lift": retrieval_help_ratio_lift,
        "transfer_pass_delta": transfer_pass_delta,
        "activation_delta": activation_delta,
        "retrieval_help_ratio_delta": retrieval_help_ratio_delta,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Run real-world CLI learning benchmark with docs/persistence ablations")
    ap.add_argument("--sessions", type=int, default=5, help="Runs per arm; use >=10 for stronger curves.")
    ap.add_argument("--start-session", type=int, default=76001)
    ap.add_argument("--max-steps", type=int, default=10)
    ap.add_argument("--learning-mode", default=BENCHMARK_DEFAULT_LEARNING_MODE, choices=LEARNING_MODES)
    ap.add_argument("--model-executor", default=DEFAULT_EXECUTOR_MODEL)
    ap.add_argument("--model-judge", default=DEFAULT_EXECUTOR_MODEL)
    ap.add_argument("--posttask-mode", choices=["candidate", "direct"], default="direct")
    ap.add_argument("--doc-budget-tokens", type=int, default=900)
    ap.add_argument("--doc-retrieval", choices=["off", "auto"], default="auto")
    ap.add_argument("--doc-retriever-model", default="")
    ap.add_argument("--llm-backend", default="anthropic", choices=["anthropic", "claude_print"])
    ap.add_argument(
        "--benchmark-deterministic",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_BENCHMARK_DETERMINISTIC,
        help="Force deterministic benchmark settings (temperature=0 for executor/judge/lesson generation).",
    )
    ap.add_argument(
        "--benchmark-promoted-only",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_BENCHMARK_PROMOTED_ONLY,
        help="Restrict retrieval to promoted lessons only (exclude candidates).",
    )
    ap.add_argument(
        "--judge-diagnostic",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run LLM judge even when deterministic contract passes to capture rationale taxonomy.",
    )
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument(
        "--suite",
        action="append",
        default=[],
        choices=["git", "sqlite", "xlsx"],
        help="Optional suite filter (repeatable).",
    )
    ap.add_argument(
        "--arm",
        action="append",
        default=[],
        help="Optional ablation arm id filter (repeatable).",
    )
    ap.add_argument(
        "--output-json",
        default=str(REPORTS_ROOT / "realworld_learning_benchmark.json"),
    )
    ap.add_argument(
        "--output-md",
        default=str(REPORTS_ROOT / "realworld_learning_benchmark.md"),
    )
    args = ap.parse_args()

    if int(args.sessions) <= 0:
        raise ValueError("--sessions must be >= 1")

    cfg = load_config()
    model_executor = args.model_executor.strip() or DEFAULT_EXECUTOR_MODEL
    # Benchmark policy: no separate critic tuning surface.
    # Keep critic aligned with executor and disable escalation for reproducibility.
    model_critic = model_executor
    model_judge = args.model_judge.strip() if args.model_judge else model_executor
    doc_retriever_model = str(args.doc_retriever_model).strip() or None
    auto_escalate_critic = False

    selected_suites = {str(item).strip() for item in args.suite if str(item).strip()}
    active_suites = [
        row for row in DOMAIN_SUITES
        if not selected_suites or str(row["suite"]) in selected_suites
    ]
    if not active_suites:
        raise ValueError("No active suites selected.")
    arms = _build_ablations()
    requested_arms = {str(item).strip() for item in args.arm if str(item).strip()}
    if requested_arms:
        arms = [row for row in arms if str(row["arm_id"]) in requested_arms]
        if not arms:
            available = ", ".join(sorted(str(row["arm_id"]) for row in _build_ablations()))
            raise ValueError(f"No matching --arm values. Available: {available}")
    task_schedule: list[dict[str, str]] = []
    for suite in active_suites:
        task_schedule.append(
            {
                "suite": str(suite["suite"]),
                "phase": "train",
                "domain": str(suite["train"]["domain"]),
                "task_id": str(suite["train"]["task_id"]),
            }
        )
        task_schedule.append(
            {
                "suite": str(suite["suite"]),
                "phase": "transfer",
                "domain": str(suite["transfer"]["domain"]),
                "task_id": str(suite["transfer"]["task_id"]),
            }
        )
    all_rows: list[dict[str, Any]] = []
    rows_by_arm: dict[str, list[dict[str, Any]]] = {str(arm["arm_id"]): [] for arm in arms}

    print(f"\n{'=' * 96}")
    print("  Real-World CLI Learning Benchmark")
    print("  suites=" + ", ".join(str(row["suite"]) for row in active_suites) + " (train/transfer)")
    print(
        f"  arms={len(arms)} sessions_per_arm={args.sessions} max_steps={args.max_steps} "
        f"learning_mode={args.learning_mode} model_executor={model_executor} "
        f"critic=executor(locked) judge_diagnostic={bool(args.judge_diagnostic)}"
    )
    print(f"{'=' * 96}\n")

    session_cursor = int(args.start_session)
    for arm in arms:
        arm_id = str(arm["arm_id"])
        _clear_learning_state()
        print(
            f"--- arm={arm_id} docs={'on' if arm['docs_enabled'] else 'off'} "
            f"doc_mode={arm['doc_mode']} lessons={'on' if arm['lessons_enabled'] else 'off'} ---"
        )
        for run_index in range(1, int(args.sessions) + 1):
            if not bool(arm["lessons_enabled"]):
                _clear_learning_state()

            task_spec = _pick_task_for_run(run_index, task_schedule)
            suite = next(item for item in DOMAIN_SUITES if str(item["suite"]) == str(task_spec["suite"]))
            docs_enabled = bool(arm["docs_enabled"])
            documentation = list(suite["docs"]) if docs_enabled else []
            doc_mode = str(arm["doc_mode"]) if docs_enabled else "none"
            doc_retrieval = args.doc_retrieval if docs_enabled else "off"
            judge_docs = docs_enabled
            executor_docs = docs_enabled

            print(
                f"  run {run_index}/{args.sessions} session={session_cursor} "
                f"suite={task_spec['suite']} phase={task_spec['phase']} task={task_spec['task_id']}"
            )
            t0 = time.time()
            result = run_cli_agent(
                cfg=cfg,
                task_id=task_spec["task_id"],
                task=None,
                session_id=session_cursor,
                max_steps=int(args.max_steps),
                domain=task_spec["domain"],
                learning_mode=args.learning_mode,
                model_executor=model_executor,
                model_critic=model_critic,
                model_judge=model_judge,
                architecture_mode="full",
                bootstrap=False,
                posttask_mode=args.posttask_mode,
                posttask_learn=bool(arm["lessons_enabled"]),
                memory_v2_demo_mode=False,
                verbose=bool(args.verbose),
                auto_escalate_critic=auto_escalate_critic,
                escalation_score_threshold=0.75,
                escalation_consecutive_runs=2,
                require_skill_read=True,
                opaque_tools=False,
                cryptic_errors=False,
                semi_helpful_errors=False,
                mixed_errors=False,
                enable_transfer_retrieval=True,
                transfer_retrieval_max_results=2,
                transfer_retrieval_score_weight=0.35,
                documentation=documentation,
                doc_mode=doc_mode,
                doc_budget_tokens=max(128, int(args.doc_budget_tokens)),
                doc_retrieval=doc_retrieval,
                doc_retriever_model=doc_retriever_model,
                judge_docs=judge_docs,
                executor_docs=executor_docs,
                judge_diagnostic=bool(args.judge_diagnostic),
                llm_backend=args.llm_backend,
                benchmark_deterministic=bool(args.benchmark_deterministic),
                benchmark_promoted_only=bool(args.benchmark_promoted_only),
            )
            metrics = result.metrics if isinstance(result.metrics, dict) else {}
            row = _build_row(
                arm=arm,
                run_index=run_index,
                session_id=session_cursor,
                elapsed_s=time.time() - t0,
                task_spec=task_spec,
                effective_doc_mode=doc_mode,
                metrics=metrics,
            )
            rows_by_arm[arm_id].append(row)
            all_rows.append(row)
            status = "PASS" if row["passed"] else "FAIL"
            print(
                f"    [{status}] score={row['score']:.2f} steps={row['steps']} "
                f"errors={row['tool_errors']} repeat_delta={row['repeated_error_delta']:+.2f} "
                f"({row['elapsed_s']:.2f}s)"
            )
            session_cursor += 1
        print()

    arms_payload: dict[str, Any] = {}
    for arm in arms:
        arm_id = str(arm["arm_id"])
        rows = rows_by_arm[arm_id]
        arms_payload[arm_id] = {
            "docs_enabled": bool(arm["docs_enabled"]),
            "doc_mode": str(arm["doc_mode"]),
            "lessons_enabled": bool(arm["lessons_enabled"]),
            "summary": _summarize(rows),
            "transfer": _transfer_summary(rows),
            "runs": rows,
        }

    payload = {
        "config": {
            "sessions_per_arm": int(args.sessions),
            "start_session": int(args.start_session),
            "max_steps": int(args.max_steps),
            "learning_mode": args.learning_mode,
            "model_executor": model_executor,
            "model_critic": model_critic,
            "model_judge": model_judge,
            "posttask_mode": args.posttask_mode,
            "doc_budget_tokens": int(args.doc_budget_tokens),
            "doc_retrieval": args.doc_retrieval,
            "doc_retriever_model": doc_retriever_model,
            "llm_backend": args.llm_backend,
            "benchmark_deterministic": bool(args.benchmark_deterministic),
            "benchmark_promoted_only": bool(args.benchmark_promoted_only),
            "auto_escalate_critic": False,
            "judge_diagnostic": bool(args.judge_diagnostic),
        },
        "task_schedule": task_schedule,
        "overall": _summarize(all_rows),
        "transfer": _transfer_summary(all_rows),
        "arms": arms_payload,
        "runs": all_rows,
    }
    payload["did_learning_improve"] = _infer_learning_gain(payload)

    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    output_md.write_text(_render_markdown(payload), encoding="utf-8")

    print(f"{'=' * 96}")
    print("  Benchmark Summary")
    print(f"{'=' * 96}")
    print(f"  did_learning_improve={payload['did_learning_improve']}")
    print(
        f"  success_rate_by_session={json.dumps(payload['overall']['success_rate_by_session'], sort_keys=True)}"
    )
    print(
        "  median_steps_to_success={steps} median_repeated_error_delta={delta} transfer_pass_rate={transfer:.2%}".format(
            steps=_format_optional(payload["overall"]["median_steps_to_success"]),
            delta=_format_optional(payload["overall"]["median_repeated_error_delta"]),
            transfer=float(payload["transfer"]["pass_rate"]),
        )
    )
    print(f"  wrote_json={output_json}")
    print(f"  wrote_md={output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
