#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _session_dir(session_id: int) -> Path:
    return Path("sessions") / f"session-{session_id:03d}"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except Exception:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _short(text: str, max_chars: int = 180) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3] + "..."


def _render_session(session_id: int, *, show_ok: bool, show_output: bool) -> str:
    base = _session_dir(session_id)
    metrics = _read_json(base / "metrics.json")
    events = _read_jsonl(base / "events.jsonl")
    if not metrics and not events:
        return f"# session-{session_id}: no artifacts found at {base}"

    lines: list[str] = []
    lines.append(f"# session-{session_id}")
    lines.append(
        "verdict: det={det} judge={judge} final={final} disagree={disagree} score={score}".format(
            det=metrics.get("eval_det_passed"),
            judge=metrics.get("judge_passed"),
            final=metrics.get("eval_final_verdict"),
            disagree=metrics.get("eval_disagreement"),
            score=metrics.get("eval_score"),
        )
    )
    lines.append(
        "runtime: model={model} steps={steps} tool_errors={errors} loop_guard_blocks={guards} elapsed_s={elapsed}".format(
            model=metrics.get("model"),
            steps=metrics.get("steps"),
            errors=metrics.get("tool_errors"),
            guards=metrics.get("loop_guard_blocks"),
            elapsed=metrics.get("elapsed_s"),
        )
    )

    if isinstance(metrics.get("eval_det_reasons"), list) and metrics.get("eval_det_reasons"):
        lines.append("det_reasons: " + ", ".join(str(x) for x in metrics.get("eval_det_reasons", [])))
    if isinstance(metrics.get("judge_reasons"), list) and metrics.get("judge_reasons"):
        lines.append("judge_reasons: " + ", ".join(str(x) for x in metrics.get("judge_reasons", [])))
    if isinstance(metrics.get("eval_reasons"), list) and metrics.get("eval_reasons"):
        lines.append("final_reasons: " + ", ".join(str(x) for x in metrics.get("eval_reasons", [])))

    lines.append("")
    lines.append("events:")
    for row in events:
        step = row.get("step")
        tool = row.get("tool")
        ok = bool(row.get("ok", False))
        if ok and not show_ok:
            continue
        state = "OK" if ok else "FAIL"
        tool_input = row.get("tool_input")
        action = None
        if isinstance(tool_input, dict):
            action = tool_input.get("action")
        lines.append(f"  step={step} tool={tool} action={action} -> {state}")
        error = str(row.get("error") or "").strip()
        if error:
            lines.append(f"    error={_short(error, 220)}")
        if show_output:
            output = row.get("output")
            if output is not None:
                if isinstance(output, (dict, list)):
                    output_text = json.dumps(output, ensure_ascii=True)
                else:
                    output_text = str(output)
                if output_text.strip():
                    lines.append(f"    output={_short(output_text, 260)}")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Render FL session timeline with referee verdict line.")
    ap.add_argument("--session", type=int, required=True)
    ap.add_argument("--show-ok", action="store_true", help="Include successful events")
    ap.add_argument("--show-output", action="store_true", help="Include compact tool output snippets")
    args = ap.parse_args()
    print(_render_session(args.session, show_ok=bool(args.show_ok), show_output=bool(args.show_output)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
