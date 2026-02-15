#!/usr/bin/env python3
"""Run A/B benchmark: architecture_mode=full vs architecture_mode=simplified."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from config import load_config
from tracks.cli_sqlite.agent_cli import (
    DEFAULT_CRITIC_MODEL,
    DEFAULT_EXECUTOR_MODEL,
    DEFAULT_LEARNING_MODE,
    ESCALATION_STATE_PATH,
    LEARNING_MODES,
    LESSONS_PATH,
    run_cli_agent,
)


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _token_estimate(metrics: dict[str, Any]) -> int:
    usage = metrics.get("usage", [])
    if not isinstance(usage, list):
        return 0
    total = 0
    for item in usage:
        if not isinstance(item, dict):
            continue
        total += _to_int(item.get("input_tokens"))
        total += _to_int(item.get("output_tokens"))
    return total


def _clear_lessons_and_escalation() -> None:
    LESSONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    LESSONS_PATH.write_text("", encoding="utf-8")
    if ESCALATION_STATE_PATH.exists():
        ESCALATION_STATE_PATH.unlink()


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    n = len(rows)
    if n == 0:
        return {
            "pass_rate": 0.0,
            "mean_score": 0.0,
            "mean_steps": 0.0,
            "mean_tool_errors": 0.0,
            "total_tokens_est": 0,
            "total_elapsed_s": 0.0,
        }
    return {
        "pass_rate": sum(1 for row in rows if row["passed"]) / n,
        "mean_score": sum(float(row["score"]) for row in rows) / n,
        "mean_steps": sum(int(row["steps"]) for row in rows) / n,
        "mean_tool_errors": sum(int(row["tool_errors"]) for row in rows) / n,
        "total_tokens_est": sum(int(row["tokens_est"]) for row in rows),
        "total_elapsed_s": sum(float(row["elapsed_s"]) for row in rows),
    }


def _render_markdown_summary(
    *,
    payload: dict[str, Any],
    full_agg: dict[str, float | int],
    simplified_agg: dict[str, float | int],
    deltas: dict[str, float | int],
) -> str:
    config = payload["config"]
    caveats = payload.get("caveats", [])
    lines = [
        "# Architecture A/B Summary",
        "",
        "## Config",
        "",
        f"- domain: `{config['domain']}`",
        f"- task_id: `{config['task_id']}`",
        f"- learning_mode: `{config['learning_mode']}`",
        f"- sessions_per_arm: `{config['sessions_per_arm']}`",
        f"- max_steps: `{config['max_steps']}`",
        f"- bootstrap: `{config['bootstrap']}`",
        f"- mixed_errors: `{config['mixed_errors']}`",
        f"- cryptic_errors: `{config['cryptic_errors']}`",
        f"- semi_helpful_errors: `{config['semi_helpful_errors']}`",
        "",
        "## Arm Metrics",
        "",
        "| arm | pass_rate | mean_score | mean_steps | mean_tool_errors | total_tokens_est | total_elapsed_s |",
        "|---|---:|---:|---:|---:|---:|---:|",
        (
            f"| full | {float(full_agg['pass_rate']):.2%} | {float(full_agg['mean_score']):.3f} | "
            f"{float(full_agg['mean_steps']):.2f} | {float(full_agg['mean_tool_errors']):.2f} | "
            f"{int(full_agg['total_tokens_est'])} | {float(full_agg['total_elapsed_s']):.2f} |"
        ),
        (
            f"| simplified | {float(simplified_agg['pass_rate']):.2%} | {float(simplified_agg['mean_score']):.3f} | "
            f"{float(simplified_agg['mean_steps']):.2f} | {float(simplified_agg['mean_tool_errors']):.2f} | "
            f"{int(simplified_agg['total_tokens_est'])} | {float(simplified_agg['total_elapsed_s']):.2f} |"
        ),
        "",
        "## Delta (simplified - full)",
        "",
        f"- pass_rate: `{float(deltas['pass_rate']):+.2%}`",
        f"- mean_score: `{float(deltas['mean_score']):+.3f}`",
        f"- mean_steps: `{float(deltas['mean_steps']):+.2f}`",
        f"- mean_tool_errors: `{float(deltas['mean_tool_errors']):+.2f}`",
        f"- total_tokens_est: `{int(deltas['total_tokens_est']):+d}`",
        f"- total_elapsed_s: `{float(deltas['total_elapsed_s']):+.2f}`",
    ]
    if caveats:
        lines.extend(["", "## Caveats", ""])
        for caveat in caveats:
            lines.append(f"- {caveat}")
    lines.append("")
    return "\n".join(lines)


def _run_agent_for_arm(
    *,
    architecture_mode: str,
    kwargs: dict[str, Any],
    architecture_mode_supported: dict[str, bool | None],
    caveats: list[str],
):
    supports_mode = architecture_mode_supported.get("value", None)

    if supports_mode is not False:
        try:
            result = run_cli_agent(architecture_mode=architecture_mode, **kwargs)
            architecture_mode_supported["value"] = True
            return result
        except TypeError as exc:
            if "architecture_mode" not in str(exc):
                raise
            architecture_mode_supported["value"] = False
            caveat = (
                "run_cli_agent in this checkout does not accept architecture_mode; "
                "arms executed with the current default architecture path."
            )
            if caveat not in caveats:
                caveats.append(caveat)

    return run_cli_agent(**kwargs)


def main() -> int:
    ap = argparse.ArgumentParser(description="A/B benchmark: architecture full vs simplified")
    ap.add_argument("--domain", default="gridtool", choices=["sqlite", "gridtool", "fluxtool"])
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--learning-mode", default=DEFAULT_LEARNING_MODE, choices=LEARNING_MODES)
    ap.add_argument("--sessions", type=int, default=5)
    ap.add_argument("--start-session", type=int, default=14001)
    ap.add_argument("--max-steps", type=int, default=8)
    ap.add_argument("--bootstrap", action="store_true")
    ap.add_argument("--mixed-errors", action="store_true")
    ap.add_argument("--cryptic-errors", action="store_true")
    ap.add_argument("--semi-helpful-errors", action="store_true")
    ap.add_argument("--model-executor", default=DEFAULT_EXECUTOR_MODEL)
    ap.add_argument("--model-critic", default=DEFAULT_CRITIC_MODEL)
    ap.add_argument("--model-judge", default=None)
    ap.add_argument("--clear-lessons-between-arms", action="store_true")
    ap.add_argument("--output-json", default="", help="Optional path to write JSON summary payload")
    ap.add_argument("--output-md", default="", help="Optional path to write Markdown summary")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    architecture_mode_supported: dict[str, bool | None] = {"value": None}
    caveats: list[str] = []

    arms: list[tuple[str, str]] = [("A", "full"), ("B", "simplified")]
    runs_by_arm: dict[str, list[dict[str, Any]]] = {"full": [], "simplified": []}
    aggregates: dict[str, dict[str, float | int]] = {}

    model_executor = args.model_executor.strip() or DEFAULT_EXECUTOR_MODEL
    model_critic = args.model_critic.strip() or DEFAULT_CRITIC_MODEL
    model_judge = args.model_judge.strip() if args.model_judge else None

    print(f"\n{'=' * 72}")
    print("  Architecture A/B Benchmark")
    print(f"  domain={args.domain} task={args.task_id} learning_mode={args.learning_mode}")
    print(f"  sessions_per_arm={args.sessions} start_session={args.start_session} max_steps={args.max_steps}")
    print(f"  bootstrap={args.bootstrap} mixed_errors={args.mixed_errors} cryptic_errors={args.cryptic_errors} semi_helpful_errors={args.semi_helpful_errors}")
    print(f"{'=' * 72}\n")

    session_cursor = args.start_session

    for arm_label, architecture_mode in arms:
        if args.clear_lessons_between_arms:
            _clear_lessons_and_escalation()
            print(f"[Arm {arm_label}] cleared lessons + escalation state")

        print(f"--- Arm {arm_label}: architecture_mode={architecture_mode} ({args.sessions} sessions) ---")
        arm_rows: list[dict[str, Any]] = []

        for i in range(args.sessions):
            run_idx = i + 1
            session_id = session_cursor + i
            print(f"  [{architecture_mode}] run {run_idx}/{args.sessions} session={session_id}")
            t0 = time.time()

            common_kwargs = {
                "cfg": cfg,
                "task_id": args.task_id,
                "task": None,
                "session_id": session_id,
                "max_steps": args.max_steps,
                "domain": args.domain,
                "learning_mode": args.learning_mode,
                "model_executor": model_executor,
                "model_critic": model_critic,
                "model_judge": model_judge,
                # Keep A/B runs comparable and non-mutating for skill files.
                "posttask_mode": "candidate",
                "posttask_learn": True,
                "verbose": args.verbose,
                "auto_escalate_critic": True,
                "escalation_score_threshold": 0.75,
                "escalation_consecutive_runs": 2,
                "require_skill_read": not args.bootstrap,
                "opaque_tools": False,
                "bootstrap": args.bootstrap,
                "cryptic_errors": args.cryptic_errors,
                "semi_helpful_errors": args.semi_helpful_errors,
                "mixed_errors": args.mixed_errors,
            }
            result = _run_agent_for_arm(
                architecture_mode=architecture_mode,
                kwargs=common_kwargs,
                architecture_mode_supported=architecture_mode_supported,
                caveats=caveats,
            )

            metrics = result.metrics
            elapsed_s = float(metrics.get("elapsed_s", 0.0) or 0.0)
            if elapsed_s <= 0:
                elapsed_s = round(time.time() - t0, 3)
            tokens_est = _token_estimate(metrics)

            row = {
                "arm": architecture_mode,
                "arm_label": arm_label,
                "run": run_idx,
                "session_id": session_id,
                "score": float(metrics.get("eval_score", 0.0) or 0.0),
                "pass": bool(metrics.get("eval_passed", False)),
                "passed": bool(metrics.get("eval_passed", False)),
                "steps": int(metrics.get("steps", 0) or 0),
                "tool_errors": int(metrics.get("tool_errors", 0) or 0),
                "lessons_loaded": int(metrics.get("lessons_loaded", 0) or 0),
                "lessons_generated": int(metrics.get("lessons_generated", 0) or 0),
                "elapsed_s": elapsed_s,
                "token_estimate": tokens_est,
                "tokens_est": tokens_est,
            }
            arm_rows.append(row)

            status = "PASS" if row["passed"] else "FAIL"
            print(
                f"    [{status}] score={row['score']:.2f} steps={row['steps']} errors={row['tool_errors']} "
                f"lessons_in={row['lessons_loaded']} lessons_out={row['lessons_generated']} "
                f"tokens_est={row['tokens_est']} ({row['elapsed_s']:.2f}s)"
            )

        runs_by_arm[architecture_mode] = arm_rows
        aggregates[architecture_mode] = _aggregate(arm_rows)
        session_cursor += args.sessions
        print()

    full_agg = aggregates["full"]
    simplified_agg = aggregates["simplified"]
    deltas = {
        "pass_rate": float(simplified_agg["pass_rate"]) - float(full_agg["pass_rate"]),
        "mean_score": float(simplified_agg["mean_score"]) - float(full_agg["mean_score"]),
        "mean_steps": float(simplified_agg["mean_steps"]) - float(full_agg["mean_steps"]),
        "mean_tool_errors": float(simplified_agg["mean_tool_errors"]) - float(full_agg["mean_tool_errors"]),
        "total_tokens_est": int(simplified_agg["total_tokens_est"]) - int(full_agg["total_tokens_est"]),
        "total_elapsed_s": float(simplified_agg["total_elapsed_s"]) - float(full_agg["total_elapsed_s"]),
    }

    print(f"{'=' * 72}")
    print("  Arm Summary")
    print(f"{'=' * 72}")
    print(
        f"{'Arm':<12} {'PassRate':>8} {'MeanScore':>10} {'MeanSteps':>10} "
        f"{'MeanErrs':>10} {'TokensEst':>12} {'Elapsed(s)':>12}"
    )
    for arm in ("full", "simplified"):
        agg = aggregates[arm]
        print(
            f"{arm:<12} "
            f"{float(agg['pass_rate']):>8.2%} "
            f"{float(agg['mean_score']):>10.3f} "
            f"{float(agg['mean_steps']):>10.2f} "
            f"{float(agg['mean_tool_errors']):>10.2f} "
            f"{int(agg['total_tokens_est']):>12} "
            f"{float(agg['total_elapsed_s']):>12.2f}"
        )

    print("\nDeltas (simplified - full):")
    print(
        "  "
        f"pass_rate={deltas['pass_rate']:+.2%}  "
        f"mean_score={deltas['mean_score']:+.3f}  "
        f"mean_steps={deltas['mean_steps']:+.2f}  "
        f"mean_tool_errors={deltas['mean_tool_errors']:+.2f}  "
        f"total_tokens_est={deltas['total_tokens_est']:+d}  "
        f"total_elapsed_s={deltas['total_elapsed_s']:+.2f}"
    )

    payload = {
        "config": {
            "domain": args.domain,
            "task_id": args.task_id,
            "learning_mode": args.learning_mode,
            "sessions_per_arm": args.sessions,
            "start_session": args.start_session,
            "max_steps": args.max_steps,
            "bootstrap": args.bootstrap,
            "mixed_errors": args.mixed_errors,
            "cryptic_errors": args.cryptic_errors,
            "semi_helpful_errors": args.semi_helpful_errors,
            "model_executor": model_executor,
            "model_critic": model_critic,
            "model_judge": model_judge,
            "clear_lessons_between_arms": args.clear_lessons_between_arms,
        },
        "arms": {
            "full": aggregates["full"],
            "simplified": aggregates["simplified"],
        },
        "deltas": deltas,
        "runs": runs_by_arm,
        "caveats": caveats,
    }
    print("\nJSON summary:")
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    print()

    if args.output_json:
        output_json = Path(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        print(f"Wrote JSON summary: {output_json}")

    if args.output_md:
        output_md = Path(args.output_md)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(
            _render_markdown_summary(
                payload=payload,
                full_agg=full_agg,
                simplified_agg=simplified_agg,
                deltas=deltas,
            ),
            encoding="utf-8",
        )
        print(f"Wrote Markdown summary: {output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
