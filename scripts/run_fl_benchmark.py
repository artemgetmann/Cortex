#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from statistics import mean
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


DEFAULT_TASK = (
    "In FL Studio, press F6 to open Channel Rack, create a 4-on-the-floor kick "
    "pattern on 808 Kick by activating steps 1,5,9,13, then press Space to "
    "start playback and press Space again to stop."
)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _session_dir(session_id: int) -> Path:
    return Path("sessions") / f"session-{session_id:03d}"


def _metrics_path(session_id: int) -> Path:
    return _session_dir(session_id) / "metrics.json"


def _events_path(session_id: int) -> Path:
    return _session_dir(session_id) / "events.jsonl"


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "run_count": 0,
            "pass_count": 0,
            "fail_count": 0,
            "uncertain_count": 0,
            "pass_rate": 0.0,
            "uncertain_rate": 0.0,
            "disagreement_rate": 0.0,
            "mean_score": 0.0,
            "mean_steps": 0.0,
            "mean_tool_errors": 0.0,
        }

    run_count = len(rows)
    pass_count = sum(1 for row in rows if row.get("eval_final_verdict") == "pass")
    fail_count = sum(1 for row in rows if row.get("eval_final_verdict") == "fail")
    uncertain_count = sum(1 for row in rows if row.get("eval_final_verdict") == "uncertain")
    disagreement_count = sum(1 for row in rows if bool(row.get("eval_disagreement", False)))

    return {
        "run_count": run_count,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "uncertain_count": uncertain_count,
        "pass_rate": round(pass_count / run_count, 4),
        "uncertain_rate": round(uncertain_count / run_count, 4),
        "disagreement_rate": round(disagreement_count / run_count, 4),
        "mean_score": round(mean(_to_float(row.get("eval_score")) for row in rows), 4),
        "mean_steps": round(mean(_to_int(row.get("steps")) for row in rows), 4),
        "mean_tool_errors": round(mean(_to_int(row.get("tool_errors")) for row in rows), 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run repeated FL Studio computer-use sessions and emit benchmark summary."
    )
    ap.add_argument("--start-session", type=int, default=200001, help="First session id in the benchmark run")
    ap.add_argument("--runs", type=int, default=10, help="How many sequential sessions to run")
    ap.add_argument("--max-steps", type=int, default=12)
    ap.add_argument("--task", default=DEFAULT_TASK)
    ap.add_argument("--model", default="", help="Override model. Default: CORTEX_MODEL_HEAVY")
    ap.add_argument("--no-skills", action="store_true")
    ap.add_argument("--no-posttask-learn", action="store_true")
    ap.add_argument("--posttask-mode", choices=["candidate", "direct"], default="candidate")
    ap.add_argument("--output-json", default="", help="Optional JSON output path")
    ap.add_argument("--print-json", action="store_true", help="Print full JSON payload to stdout")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if args.runs <= 0:
        raise SystemExit("--runs must be > 0")

    # Keep heavy runtime imports inside main so `--help` works even on machines
    # without macOS Quartz bindings installed.
    from agent import run_agent
    from config import load_config

    cfg = load_config()
    model = args.model.strip() or cfg.model_heavy

    rows: list[dict[str, Any]] = []
    started_at = time.time()
    for offset in range(args.runs):
        session_id = args.start_session + offset
        print(
            f"== FL run {offset + 1}/{args.runs} session={session_id} model={model} max_steps={args.max_steps}",
            flush=True,
        )
        result = run_agent(
            cfg=cfg,
            task=args.task,
            session_id=session_id,
            max_steps=args.max_steps,
            model=model,
            load_skills=not args.no_skills,
            posttask_learn=not args.no_posttask_learn,
            posttask_mode=args.posttask_mode,
            verbose=args.verbose,
        )
        metrics = result.metrics
        row = {
            "session_id": session_id,
            "eval_final_verdict": str(metrics.get("eval_final_verdict", "unknown")),
            "eval_passed": bool(metrics.get("eval_passed", False)),
            "eval_score": _to_float(metrics.get("eval_score")),
            "eval_disagreement": bool(metrics.get("eval_disagreement", False)),
            "eval_det_passed": metrics.get("eval_det_passed"),
            "eval_det_score": metrics.get("eval_det_score"),
            "judge_passed": metrics.get("judge_passed"),
            "judge_score": metrics.get("judge_score"),
            "judge_confidence": metrics.get("judge_confidence"),
            "steps": _to_int(metrics.get("steps")),
            "tool_errors": _to_int(metrics.get("tool_errors")),
            "loop_guard_blocks": _to_int(metrics.get("loop_guard_blocks")),
            "elapsed_s": round(_to_float(metrics.get("elapsed_s")), 3),
            "metrics_path": str(_metrics_path(session_id)),
            "events_path": str(_events_path(session_id)),
        }
        rows.append(row)
        print(
            "   verdict={verdict} det={det} judge={judge} score={score:.2f} steps={steps} errors={errors}".format(
                verdict=row["eval_final_verdict"],
                det=row.get("eval_det_passed"),
                judge=row.get("judge_passed"),
                score=row["eval_score"],
                steps=row["steps"],
                errors=row["tool_errors"],
            ),
            flush=True,
        )

    summary = _summarize(rows)
    payload = {
        "config": {
            "start_session": args.start_session,
            "runs": args.runs,
            "max_steps": args.max_steps,
            "task": args.task,
            "model": model,
            "load_skills": not args.no_skills,
            "posttask_learn": not args.no_posttask_learn,
            "posttask_mode": args.posttask_mode,
        },
        "summary": summary,
        "runs": rows,
        "elapsed_s": round(time.time() - started_at, 3),
    }

    print("")
    print("Summary:")
    print(
        "  pass={pass_count}/{run_count} fail={fail_count} uncertain={uncertain_count} "
        "pass_rate={pass_rate:.2%} disagreement_rate={disagreement_rate:.2%}".format(**summary)
    )
    print(
        "  mean_score={mean_score:.3f} mean_steps={mean_steps:.2f} mean_tool_errors={mean_tool_errors:.2f}".format(
            **summary
        )
    )

    if args.output_json:
        out = Path(args.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        print(f"  wrote_json={out}")

    if args.print_json:
        print("")
        print(json.dumps(payload, indent=2, ensure_ascii=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
