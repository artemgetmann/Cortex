#!/usr/bin/env python3
"""Run the FL Studio 4-on-the-floor demo via the CLI agent harness."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from config import load_config
from tracks.cli_sqlite import agent_cli
from tracks.cli_sqlite.agent_cli import (
    DEFAULT_ARCHITECTURE_MODE,
    DEFAULT_CRITIC_MODEL,
    DEFAULT_EXECUTOR_MODEL,
    DEFAULT_LEARNING_MODE,
    DEFAULT_TRANSFER_RETRIEVAL_MAX_RESULTS,
    DEFAULT_TRANSFER_RETRIEVAL_SCORE_WEIGHT,
    LEARNING_MODES,
    ARCHITECTURE_MODES,
    run_cli_agent,
)


@dataclass(frozen=True)
class PhaseSpec:
    name: str
    title: str
    task_text: str
    judge_reference: str


PHASES: tuple[PhaseSpec, ...] = (
    PhaseSpec(
        name="channel_rack_focus",
        title="Channel Rack focus",
        task_text=(
            "Phase 1: Press F6 to open the Channel Rack, locate the Kick row (top row), "
            "confirm it is unmuted, and keep the row selected. Once focused, capture how many rows \"Kick\" shows in the Hint Bar, but do not activate any steps yet."
        ),
        judge_reference="channel_rack_focus",
    ),
    PhaseSpec(
        name="kick_pattern_programming",
        title="Kick pattern programming",
        task_text=(
            "Phase 2: Click the Kick row steps 1, 5, 9, and 13 exactly once to create the 4-on-the-floor pattern. "
            "If a step misfires, undo with Cmd+Z and finish only the missing step so the four key buttons are lit."  # noqa: E501
        ),
        judge_reference="kick_step_clicks",
    ),
    PhaseSpec(
        name="transport_verification",
        title="Transport verification",
        task_text=(
            "Phase 3: Press Space to start playback, let the transport run for four beats, "
            "confirm the timer advances, then press Space again to stop. Capture a screenshot while playback is running, showing the transport indicator incrementing.",
        ),
        judge_reference="playback_screenshot",
    ),
)


def _session_dir(session_id: int) -> Path:
    return agent_cli.SESSIONS_ROOT / f"session-{session_id:03d}"


def _collect_screenshots(session_id: int, max_screenshots: int) -> list[str]:
    if max_screenshots <= 0:
        return []
    session_dir = _session_dir(session_id)
    if not session_dir.exists():
        return []
    images = sorted(session_dir.glob("*.png"))
    if not images:
        return []
    return [str(img) for img in images[:max_screenshots]]


def _phase_summary_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"phase_count": 0, "pass_rate": 0.0, "total_screenshots": 0, "sessions": []}
    pass_count = sum(1 for row in rows if row.get("passed"))
    return {
        "phase_count": len(rows),
        "pass_rate": pass_count / len(rows),
        "total_screenshots": sum(len(row.get("screenshots", [])) for row in rows),
        "sessions": [row.get("session_id") for row in rows],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the FL Studio 4-on-the-floor demo via run_cli_agent.")
    ap.add_argument("--session", type=int, default=9801, help="Starting session id for the phase runs")
    ap.add_argument("--task-id", default="fl_studio_demo", help="Task id that points to the demo instructions")
    ap.add_argument("--max-steps", type=int, default=12)
    ap.add_argument("--domain", default="sqlite", choices=["sqlite", "gridtool", "fluxtool", "artic", "shell"])
    ap.add_argument("--learning-mode", default=DEFAULT_LEARNING_MODE, choices=LEARNING_MODES)
    ap.add_argument("--architecture-mode", default=DEFAULT_ARCHITECTURE_MODE, choices=ARCHITECTURE_MODES)
    ap.add_argument("--model-executor", default=DEFAULT_EXECUTOR_MODEL)
    ap.add_argument("--model-critic", default=DEFAULT_CRITIC_MODEL)
    ap.add_argument("--model-judge", default=None)
    ap.add_argument("--posttask-mode", choices=["candidate", "direct"], default="candidate")
    ap.add_argument("--no-posttask-learn", action="store_true")
    ap.add_argument("--memory-v2-demo-mode", action="store_true")
    ap.add_argument("--bootstrap", action="store_true", help="Run without skill docs")
    ap.add_argument("--cryptic-errors", action="store_true")
    ap.add_argument("--semi-helpful-errors", action="store_true")
    ap.add_argument("--mixed-errors", action="store_true")
    ap.add_argument("--enable-transfer-retrieval", action="store_true")
    ap.add_argument("--transfer-retrieval-max-results", type=int, default=DEFAULT_TRANSFER_RETRIEVAL_MAX_RESULTS)
    ap.add_argument(
        "--transfer-retrieval-score-weight",
        type=float,
        default=DEFAULT_TRANSFER_RETRIEVAL_SCORE_WEIGHT,
    )
    ap.add_argument("--opaque-tools", action="store_true")
    ap.add_argument("--max-screenshots", type=int, default=3)
    ap.add_argument("--output-json", default="", help="Optional path to write JSON summary")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    cfg = load_config()

    current_session = args.session
    rows: list[dict[str, Any]] = []

    for phase in PHASES:
        print(f"--- Phase {phase.title} (session {current_session}) ---")
        result = run_cli_agent(
            cfg=cfg,
            task_id=args.task_id,
            task=phase.task_text,
            session_id=current_session,
            max_steps=args.max_steps,
            domain=args.domain,
            learning_mode=args.learning_mode,
            architecture_mode=args.architecture_mode,
            model_executor=args.model_executor.strip() or DEFAULT_EXECUTOR_MODEL,
            model_critic=args.model_critic.strip() or DEFAULT_CRITIC_MODEL,
            model_judge=args.model_judge.strip() if args.model_judge else None,
            posttask_mode=args.posttask_mode,
            posttask_learn=not args.no_posttask_learn,
            memory_v2_demo_mode=bool(args.memory_v2_demo_mode),
            verbose=args.verbose,
            auto_escalate_critic=True,
            escalation_score_threshold=0.75,
            escalation_consecutive_runs=2,
            require_skill_read=not args.bootstrap,
            opaque_tools=bool(args.opaque_tools),
            bootstrap=bool(args.bootstrap),
            cryptic_errors=bool(args.cryptic_errors),
            semi_helpful_errors=bool(args.semi_helpful_errors),
            mixed_errors=bool(args.mixed_errors),
            enable_transfer_retrieval=bool(args.enable_transfer_retrieval),
            transfer_retrieval_max_results=max(0, args.transfer_retrieval_max_results),
            transfer_retrieval_score_weight=max(0.0, args.transfer_retrieval_score_weight),
        )

        phase_screenshots = _collect_screenshots(current_session, args.max_screenshots)
        metrics = result.metrics if hasattr(result, "metrics") else {}
        score = float(metrics.get("eval_score", 0.0) or 0.0)
        passed = bool(metrics.get("eval_passed", False))

        row = {
            "phase": phase.name,
            "title": phase.title,
            "judge_reference": phase.judge_reference,
            "session_id": current_session,
            "task_text": phase.task_text,
            "metrics": metrics,
            "score": score,
            "passed": passed,
            "screenshots": phase_screenshots,
        }
        rows.append(row)

        status = "PASS" if passed else "FAIL"
        print(
            f"  {phase.name}: session={current_session} {status} score={score:.2f} "
            f"screenshots={len(phase_screenshots)}"
        )
        print()

        current_session += 1

    summary = _phase_summary_rows(rows)
    payload = {
        "config": {
            "task_id": args.task_id,
            "domain": args.domain,
            "max_steps": args.max_steps,
            "learning_mode": args.learning_mode,
            "architecture_mode": args.architecture_mode,
            "model_executor": args.model_executor,
            "model_critic": args.model_critic,
            "model_judge": args.model_judge,
            "posttask_mode": args.posttask_mode,
            "memory_v2_demo_mode": bool(args.memory_v2_demo_mode),
            "bootstrap": bool(args.bootstrap),
            "transfer_retrieval_enabled": bool(args.enable_transfer_retrieval),
        },
        "phases": rows,
        "summary": summary,
    }

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        print(f"\nWrote JSON summary: {output_path}")

    print("\nJSON summary:")
    print(json.dumps(payload, indent=2, ensure_ascii=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
