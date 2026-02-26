#!/usr/bin/env python3
"""Run realworld benchmark twice (self-edit OFF/ON) and emit a compare report."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TRACK_ROOT = Path(__file__).resolve().parents[1]
REPORTS_ROOT = TRACK_ROOT / "reports"
REALWORLD_RUNNER = TRACK_ROOT / "scripts" / "run_realworld_learning_benchmark.py"

DEFAULT_SESSIONS = 5
DEFAULT_SUITE = "sqlite"
DEFAULT_ARM = "docs_on__mode_lossy__lessons_on"
DEFAULT_START_SESSION = 93001
DEFAULT_MAX_STEPS = 6
DEFAULT_LEARNING_MODE = "strict"
DEFAULT_POSTTASK_MODE = "direct"
DEFAULT_LLM_BACKEND = "anthropic"
DEFAULT_COST_PROFILE = "cheap"


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_optional(value: float | None, precision: int = 4) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.{precision}f}"


def _extract_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    overall = payload.get("overall", {})
    transfer = payload.get("transfer", {})
    return {
        "did_learning_improve": bool(payload.get("did_learning_improve", False)),
        "overall_pass_rate": _as_float(overall.get("pass_rate", 0.0), default=0.0),
        "overall_median_steps_to_success": _as_optional_float(overall.get("median_steps_to_success")),
        "transfer_pass_rate": _as_float(transfer.get("pass_rate", 0.0), default=0.0),
        "transfer_median_steps_to_success": _as_optional_float(transfer.get("median_steps_to_success")),
        "transfer_median_repeated_error_delta": _as_optional_float(transfer.get("median_repeated_error_delta")),
        "transfer_mean_lesson_activations": _as_float(transfer.get("mean_lesson_activations", 0.0), default=0.0),
        "transfer_mean_retrieval_help_ratio": _as_float(
            transfer.get("mean_retrieval_help_ratio", 0.0), default=0.0
        ),
    }


def _improvement_delta(
    baseline_value: float | None,
    experiment_value: float | None,
) -> float | None:
    if baseline_value is None or experiment_value is None:
        return None
    # Positive means experiment improved versus baseline.
    return float(baseline_value) - float(experiment_value)


def _compute_deltas(
    *,
    self_edit_on: dict[str, Any],
    self_edit_off: dict[str, Any],
) -> dict[str, Any]:
    return {
        "did_learning_improve_delta": int(bool(self_edit_on["did_learning_improve"]))
        - int(bool(self_edit_off["did_learning_improve"])),
        "overall_pass_rate_delta": float(self_edit_on["overall_pass_rate"]) - float(self_edit_off["overall_pass_rate"]),
        "transfer_pass_rate_delta": float(self_edit_on["transfer_pass_rate"]) - float(self_edit_off["transfer_pass_rate"]),
        "transfer_median_steps_to_success_improvement": _improvement_delta(
            self_edit_off["transfer_median_steps_to_success"],
            self_edit_on["transfer_median_steps_to_success"],
        ),
        "transfer_median_repeated_error_improvement": _improvement_delta(
            self_edit_off["transfer_median_repeated_error_delta"],
            self_edit_on["transfer_median_repeated_error_delta"],
        ),
        "transfer_mean_lesson_activations_delta": float(self_edit_on["transfer_mean_lesson_activations"])
        - float(self_edit_off["transfer_mean_lesson_activations"]),
        "transfer_mean_retrieval_help_ratio_delta": float(self_edit_on["transfer_mean_retrieval_help_ratio"])
        - float(self_edit_off["transfer_mean_retrieval_help_ratio"]),
    }


def _verdict_from_deltas(deltas: dict[str, Any]) -> tuple[str, str]:
    eps = 1e-9
    transfer_delta = float(deltas.get("transfer_pass_rate_delta", 0.0))
    overall_delta = float(deltas.get("overall_pass_rate_delta", 0.0))
    steps_improvement = deltas.get("transfer_median_steps_to_success_improvement")
    non_regressing_steps = steps_improvement is None or float(steps_improvement) >= -eps

    if transfer_delta > eps:
        return ("improved", "transfer pass rate increased with self-edit ON")
    if abs(transfer_delta) <= eps and overall_delta > eps and non_regressing_steps:
        return ("improved", "transfer pass rate tied, but overall pass rate improved without slower transfer convergence")
    return ("no_improvement", "self-edit ON did not beat OFF on transfer-first criteria")


def build_compare_payload(
    *,
    self_edit_on_payload: dict[str, Any],
    self_edit_off_payload: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    on_metrics = _extract_metrics(self_edit_on_payload)
    off_metrics = _extract_metrics(self_edit_off_payload)
    deltas = _compute_deltas(self_edit_on=on_metrics, self_edit_off=off_metrics)
    verdict, reason = _verdict_from_deltas(deltas)
    return {
        "config": config,
        "self_edit_on": {
            "summary": on_metrics,
            "source_did_learning_improve": bool(self_edit_on_payload.get("did_learning_improve", False)),
            "source_transfer": self_edit_on_payload.get("transfer", {}),
            "source_overall": self_edit_on_payload.get("overall", {}),
        },
        "self_edit_off": {
            "summary": off_metrics,
            "source_did_learning_improve": bool(self_edit_off_payload.get("did_learning_improve", False)),
            "source_transfer": self_edit_off_payload.get("transfer", {}),
            "source_overall": self_edit_off_payload.get("overall", {}),
        },
        "deltas": deltas,
        "verdict": verdict,
        "verdict_reason": reason,
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    on_metrics = payload["self_edit_on"]["summary"]
    off_metrics = payload["self_edit_off"]["summary"]
    deltas = payload["deltas"]
    lines = [
        "# SAGE Self-Edit ON/OFF Compare",
        "",
        "## Verdict",
        "",
        f"- verdict: `{payload['verdict']}`",
        f"- reason: `{payload['verdict_reason']}`",
        "",
        "## Transfer-First Metrics",
        "",
        "| metric | self_edit_off | self_edit_on | delta_or_improvement |",
        "|---|---:|---:|---:|",
        (
            "| transfer_pass_rate | "
            f"{float(off_metrics['transfer_pass_rate']):.2%} | "
            f"{float(on_metrics['transfer_pass_rate']):.2%} | "
            f"{float(deltas['transfer_pass_rate_delta']):+.4f} |"
        ),
        (
            "| overall_pass_rate | "
            f"{float(off_metrics['overall_pass_rate']):.2%} | "
            f"{float(on_metrics['overall_pass_rate']):.2%} | "
            f"{float(deltas['overall_pass_rate_delta']):+.4f} |"
        ),
        (
            "| transfer_median_steps_to_success (improvement=off-on) | "
            f"{_format_optional(off_metrics['transfer_median_steps_to_success'])} | "
            f"{_format_optional(on_metrics['transfer_median_steps_to_success'])} | "
            f"{_format_optional(deltas['transfer_median_steps_to_success_improvement'])} |"
        ),
        (
            "| transfer_median_repeated_error_delta (improvement=off-on) | "
            f"{_format_optional(off_metrics['transfer_median_repeated_error_delta'])} | "
            f"{_format_optional(on_metrics['transfer_median_repeated_error_delta'])} | "
            f"{_format_optional(deltas['transfer_median_repeated_error_improvement'])} |"
        ),
        (
            "| transfer_mean_lesson_activations | "
            f"{float(off_metrics['transfer_mean_lesson_activations']):.4f} | "
            f"{float(on_metrics['transfer_mean_lesson_activations']):.4f} | "
            f"{float(deltas['transfer_mean_lesson_activations_delta']):+.4f} |"
        ),
        (
            "| transfer_mean_retrieval_help_ratio | "
            f"{float(off_metrics['transfer_mean_retrieval_help_ratio']):.4f} | "
            f"{float(on_metrics['transfer_mean_retrieval_help_ratio']):.4f} | "
            f"{float(deltas['transfer_mean_retrieval_help_ratio_delta']):+.4f} |"
        ),
        (
            "| did_learning_improve (runner-level) | "
            f"{int(bool(off_metrics['did_learning_improve']))} | "
            f"{int(bool(on_metrics['did_learning_improve']))} | "
            f"{int(deltas['did_learning_improve_delta']):+d} |"
        ),
        "",
        "## Config",
        "",
        f"- sessions: `{payload['config']['sessions']}`",
        f"- suite: `{', '.join(payload['config']['suites'])}`",
        f"- arm: `{', '.join(payload['config']['arms'])}`",
        f"- benchmark_deterministic: `{payload['config']['benchmark_deterministic']}`",
        f"- benchmark_promoted_only: `{payload['config']['benchmark_promoted_only']}`",
        f"- llm_backend: `{payload['config']['llm_backend']}`",
        f"- cost_profile: `{payload['config']['cost_profile']}`",
        "",
        "## Artifacts",
        "",
        f"- self_edit_off_json: `{payload['config']['self_edit_off_json']}`",
        f"- self_edit_on_json: `{payload['config']['self_edit_on_json']}`",
    ]
    lines.append("")
    return "\n".join(lines)


def _write_compare_reports(payload: dict[str, Any], *, output_json: Path, output_md: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    output_md.write_text(_render_markdown(payload), encoding="utf-8")


def _append_bool_flag(cmd: list[str], *, name: str, value: bool) -> None:
    cmd.append(f"--{name}" if bool(value) else f"--no-{name}")


def _run_realworld_once(
    *,
    sessions: int,
    start_session: int,
    max_steps: int,
    learning_mode: str,
    posttask_mode: str,
    self_edit_mode: bool,
    llm_backend: str,
    cost_profile: str,
    model_executor: str,
    model_judge: str,
    doc_budget_tokens: int,
    doc_retrieval: str,
    doc_retriever_model: str,
    benchmark_deterministic: bool,
    benchmark_promoted_only: bool,
    judge_diagnostic: bool,
    suites: list[str],
    arms: list[str],
    output_json: Path,
    output_md: Path,
    verbose: bool,
) -> None:
    cmd: list[str] = [
        sys.executable,
        str(REALWORLD_RUNNER),
        "--sessions",
        str(int(sessions)),
        "--start-session",
        str(int(start_session)),
        "--max-steps",
        str(int(max_steps)),
        "--learning-mode",
        learning_mode,
        "--posttask-mode",
        posttask_mode,
        "--llm-backend",
        llm_backend,
        "--cost-profile",
        cost_profile,
        "--doc-budget-tokens",
        str(int(doc_budget_tokens)),
        "--doc-retrieval",
        doc_retrieval,
        "--output-json",
        str(output_json),
        "--output-md",
        str(output_md),
    ]
    if model_executor.strip():
        cmd.extend(["--model-executor", model_executor.strip()])
    if model_judge.strip():
        cmd.extend(["--model-judge", model_judge.strip()])
    if doc_retriever_model.strip():
        cmd.extend(["--doc-retriever-model", doc_retriever_model.strip()])
    for suite in suites:
        cmd.extend(["--suite", suite])
    for arm in arms:
        cmd.extend(["--arm", arm])

    _append_bool_flag(cmd, name="self-edit-mode", value=self_edit_mode)
    _append_bool_flag(cmd, name="benchmark-deterministic", value=benchmark_deterministic)
    _append_bool_flag(cmd, name="benchmark-promoted-only", value=benchmark_promoted_only)
    _append_bool_flag(cmd, name="judge-diagnostic", value=judge_diagnostic)
    if verbose:
        cmd.append("--verbose")

    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=False)
    if int(result.returncode) != 0:
        raise RuntimeError(
            f"realworld benchmark failed for self_edit_mode={self_edit_mode} with code={result.returncode}"
        )


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Run realworld benchmark with self-edit OFF/ON compare output.")
    ap.add_argument("--sessions", type=int, default=DEFAULT_SESSIONS)
    ap.add_argument("--start-session", type=int, default=DEFAULT_START_SESSION)
    ap.add_argument(
        "--start-session-on",
        type=int,
        default=None,
        help="Optional override for self-edit ON run start session. Default: start_session + sessions + 100.",
    )
    ap.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
    ap.add_argument("--learning-mode", default=DEFAULT_LEARNING_MODE)
    ap.add_argument("--posttask-mode", choices=["candidate", "direct"], default=DEFAULT_POSTTASK_MODE)
    ap.add_argument("--llm-backend", default=DEFAULT_LLM_BACKEND)
    ap.add_argument("--cost-profile", choices=["default", "cheap"], default=DEFAULT_COST_PROFILE)
    ap.add_argument("--model-executor", default="")
    ap.add_argument("--model-judge", default="")
    ap.add_argument("--doc-budget-tokens", type=int, default=900)
    ap.add_argument("--doc-retrieval", choices=["off", "auto"], default="auto")
    ap.add_argument("--doc-retriever-model", default="")
    ap.add_argument("--suite", action="append", default=[], choices=["git", "sqlite", "xlsx"])
    ap.add_argument("--arm", action="append", default=[])
    ap.add_argument(
        "--benchmark-deterministic",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    ap.add_argument(
        "--benchmark-promoted-only",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    ap.add_argument(
        "--judge-diagnostic",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument(
        "--self-edit-off-json",
        default=str(REPORTS_ROOT / "sage_self_edit_off.json"),
    )
    ap.add_argument(
        "--self-edit-off-md",
        default=str(REPORTS_ROOT / "sage_self_edit_off.md"),
    )
    ap.add_argument(
        "--self-edit-on-json",
        default=str(REPORTS_ROOT / "sage_self_edit_on.json"),
    )
    ap.add_argument(
        "--self-edit-on-md",
        default=str(REPORTS_ROOT / "sage_self_edit_on.md"),
    )
    ap.add_argument(
        "--output-json",
        default=str(REPORTS_ROOT / "sage_self_edit_on_off_compare.json"),
    )
    ap.add_argument(
        "--output-md",
        default=str(REPORTS_ROOT / "sage_self_edit_on_off_compare.md"),
    )
    args = ap.parse_args()

    if int(args.sessions) <= 0:
        raise ValueError("--sessions must be >= 1")
    if int(args.max_steps) <= 0:
        raise ValueError("--max-steps must be >= 1")

    suites = [str(item).strip() for item in args.suite if str(item).strip()]
    arms = [str(item).strip() for item in args.arm if str(item).strip()]
    if not suites:
        suites = [DEFAULT_SUITE]
    if not arms:
        arms = [DEFAULT_ARM]

    start_session_off = int(args.start_session)
    start_session_on = int(args.start_session_on) if args.start_session_on is not None else (start_session_off + int(args.sessions) + 100)
    if start_session_on <= start_session_off:
        raise ValueError("--start-session-on must be greater than --start-session")

    off_json = Path(args.self_edit_off_json)
    off_md = Path(args.self_edit_off_md)
    on_json = Path(args.self_edit_on_json)
    on_md = Path(args.self_edit_on_md)

    print("=" * 96)
    print("  SAGE Benchmark Runner: self-edit OFF vs ON")
    print(
        f"  sessions={args.sessions} suites={','.join(suites)} arms={','.join(arms)} "
        f"deterministic={bool(args.benchmark_deterministic)} promoted_only={bool(args.benchmark_promoted_only)}"
    )
    print("=" * 96)

    _run_realworld_once(
        sessions=int(args.sessions),
        start_session=start_session_off,
        max_steps=int(args.max_steps),
        learning_mode=str(args.learning_mode),
        posttask_mode=str(args.posttask_mode),
        self_edit_mode=False,
        llm_backend=str(args.llm_backend),
        cost_profile=str(args.cost_profile),
        model_executor=str(args.model_executor),
        model_judge=str(args.model_judge),
        doc_budget_tokens=int(args.doc_budget_tokens),
        doc_retrieval=str(args.doc_retrieval),
        doc_retriever_model=str(args.doc_retriever_model),
        benchmark_deterministic=bool(args.benchmark_deterministic),
        benchmark_promoted_only=bool(args.benchmark_promoted_only),
        judge_diagnostic=bool(args.judge_diagnostic),
        suites=suites,
        arms=arms,
        output_json=off_json,
        output_md=off_md,
        verbose=bool(args.verbose),
    )
    _run_realworld_once(
        sessions=int(args.sessions),
        start_session=start_session_on,
        max_steps=int(args.max_steps),
        learning_mode=str(args.learning_mode),
        posttask_mode=str(args.posttask_mode),
        self_edit_mode=True,
        llm_backend=str(args.llm_backend),
        cost_profile=str(args.cost_profile),
        model_executor=str(args.model_executor),
        model_judge=str(args.model_judge),
        doc_budget_tokens=int(args.doc_budget_tokens),
        doc_retrieval=str(args.doc_retrieval),
        doc_retriever_model=str(args.doc_retriever_model),
        benchmark_deterministic=bool(args.benchmark_deterministic),
        benchmark_promoted_only=bool(args.benchmark_promoted_only),
        judge_diagnostic=bool(args.judge_diagnostic),
        suites=suites,
        arms=arms,
        output_json=on_json,
        output_md=on_md,
        verbose=bool(args.verbose),
    )

    compare_payload = build_compare_payload(
        self_edit_on_payload=_load_json(on_json),
        self_edit_off_payload=_load_json(off_json),
        config={
            "sessions": int(args.sessions),
            "start_session_off": start_session_off,
            "start_session_on": start_session_on,
            "max_steps": int(args.max_steps),
            "learning_mode": str(args.learning_mode),
            "posttask_mode": str(args.posttask_mode),
            "llm_backend": str(args.llm_backend),
            "cost_profile": str(args.cost_profile),
            "benchmark_deterministic": bool(args.benchmark_deterministic),
            "benchmark_promoted_only": bool(args.benchmark_promoted_only),
            "judge_diagnostic": bool(args.judge_diagnostic),
            "suites": suites,
            "arms": arms,
            "self_edit_off_json": str(off_json),
            "self_edit_on_json": str(on_json),
        },
    )
    compare_json = Path(args.output_json)
    compare_md = Path(args.output_md)
    _write_compare_reports(compare_payload, output_json=compare_json, output_md=compare_md)

    print("=" * 96)
    print("  SAGE Compare Summary")
    print("=" * 96)
    print(f"  verdict={compare_payload['verdict']}")
    print(f"  reason={compare_payload['verdict_reason']}")
    print(f"  transfer_pass_rate_delta={compare_payload['deltas']['transfer_pass_rate_delta']:+.4f}")
    print(f"  overall_pass_rate_delta={compare_payload['deltas']['overall_pass_rate_delta']:+.4f}")
    print(f"  wrote_json={compare_json}")
    print(f"  wrote_md={compare_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
