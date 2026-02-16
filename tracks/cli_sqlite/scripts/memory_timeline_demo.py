#!/usr/bin/env python3
"""Render a human-readable Memory V2 timeline from session artifacts.

This script is designed for demo/debug use: it converts session JSONL logs into
an explicit step trace showing:
- executor attempts
- failures with fingerprints/tags
- injected hint bullets
- final session outcome
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tracks.cli_sqlite.lesson_store_v2 import load_lesson_records


TRACK_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SESSIONS_ROOT = TRACK_ROOT / "sessions"
DEFAULT_LESSONS_PATH = TRACK_ROOT / "learning" / "lessons_v2.jsonl"
HINT_MARKER = "--- HINT from prior sessions ---"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _session_dir(root: Path, session_id: int) -> Path:
    return root / f"session-{session_id}"


def _short(text: str, *, max_chars: int = 180) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3] + "..."


def _extract_hints(error_text: str, *, max_hints: int = 4) -> list[str]:
    if HINT_MARKER not in error_text:
        return []
    tail = error_text.split(HINT_MARKER, 1)[1]
    hints: list[str] = []
    for line in tail.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        hints.append(stripped[2:].strip())
        if len(hints) >= max_hints:
            break
    return hints


def _step_of_memory_event(row: dict[str, Any]) -> int:
    # New events may include top-level step; older rows put it in metadata.
    raw = row.get("step")
    if isinstance(raw, int):
        return raw
    metadata = row.get("metadata", {})
    if isinstance(metadata, dict) and isinstance(metadata.get("step"), int):
        return int(metadata["step"])
    return -1


def _group_memory_events_by_step(rows: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        step = _step_of_memory_event(row)
        if step < 0:
            continue
        grouped.setdefault(step, []).append(row)
    return grouped


def _is_executor_tool(name: str) -> bool:
    lowered = str(name).strip().lower()
    return lowered in {"run_gridtool", "run_fluxtool", "run_sqlite"}


def _extract_attempt_text(tool_input: Any, *, tool_name: str) -> str:
    """
    Extract a readable command/query from heterogeneous tool payloads.

    Different domains use different field names (`command`, `commands`, `sql`),
    so the viewer probes known keys first, then falls back to compact JSON.
    """
    if not isinstance(tool_input, dict):
        return str(tool_input)
    for key in ("commands", "command", "sql", "query", "script"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if str(tool_name).strip().lower() == "show_fixture":
        value = tool_input.get("path_ref")
        if isinstance(value, str) and value.strip():
            return f"show_fixture {value.strip()}"
    try:
        return json.dumps(tool_input, ensure_ascii=True, sort_keys=True)
    except Exception:
        return str(tool_input)


def _format_multiline(text: str, *, max_chars: int = 1600, line_prefix: str = "      ") -> list[str]:
    raw = str(text or "").rstrip()
    if not raw:
        return []
    clipped = raw if len(raw) <= max_chars else raw[: max_chars - 3] + "..."
    lines: list[str] = []
    for idx, row in enumerate(clipped.splitlines(), start=1):
        lines.append(f"{line_prefix}{idx:02d} | {row}")
    if not lines:
        lines.append(f"{line_prefix}01 | {clipped}")
    return lines


def _render_lesson_snapshot(
    *,
    lessons_path: Path,
    domain: str,
    task_id: str,
    max_rows: int,
) -> list[str]:
    if max_rows <= 0:
        return []
    records = load_lesson_records(lessons_path)
    if not records:
        return ["  lessons: none"]
    scoped = [row for row in records if row.domain == domain and (not row.task_id or row.task_id == task_id)]
    if not scoped:
        return [f"  lessons: no rows for domain={domain} task={task_id}"]
    by_status: dict[str, int] = {}
    for row in scoped:
        by_status[row.status] = by_status.get(row.status, 0) + 1
    status_text = ", ".join(f"{status}={count}" for status, count in sorted(by_status.items()))
    lines = [f"  lessons: total={len(scoped)} ({status_text})"]
    ranked = sorted(
        scoped,
        key=lambda row: (
            row.status != "promoted",
            -float(row.reliability),
            -len(row.utility_history),
            row.updated_at,
        ),
    )
    for row in ranked[:max_rows]:
        tag_text = ",".join(row.tags[:3]) if row.tags else "generic"
        lines.append(
            "    - {lid} [{status}] rel={rel:.2f} uses={uses} helpful={helpful} harmful={harmful} tags={tags} :: {text}".format(
                lid=row.lesson_id,
                status=row.status,
                rel=float(row.reliability),
                uses=int(row.retrieval_count),
                helpful=int(row.helpful_count),
                harmful=int(row.harmful_count),
                tags=tag_text,
                text=_short(row.rule_text, max_chars=160),
            )
        )
    return lines


def _render_session(
    *,
    sessions_root: Path,
    session_id: int,
    max_hints_per_step: int,
    show_ok_steps: bool,
    show_all_tools: bool,
    show_tool_output: bool,
    max_output_chars: int,
    lessons_path: Path,
    show_lessons: int,
) -> str:
    base = _session_dir(sessions_root, session_id)
    metrics = _read_json(base / "metrics.json")
    events = _read_jsonl(base / "events.jsonl")
    memory_events = _read_jsonl(base / "memory_events.jsonl")
    memory_by_step = _group_memory_events_by_step(memory_events)

    lines: list[str] = []
    if not metrics and not events:
        return f"Session {session_id}: no artifacts found in {base}"

    status = "PASS" if bool(metrics.get("eval_passed", False)) else "FAIL"
    lines.append(
        "Session {sid} [{status}] domain={domain} task={task} score={score:.2f} steps={steps} errors={errors} activations={acts}".format(
            sid=session_id,
            status=status,
            domain=str(metrics.get("domain", "?")),
            task=str(metrics.get("task_id", "?")),
            score=float(metrics.get("eval_score", 0.0) or 0.0),
            steps=int(metrics.get("steps", 0) or 0),
            errors=int(metrics.get("tool_errors", 0) or 0),
            acts=int(metrics.get("lesson_activations", 0) or 0),
        )
    )
    lines.extend(
        _render_lesson_snapshot(
            lessons_path=lessons_path,
            domain=str(metrics.get("domain", "")).strip(),
            task_id=str(metrics.get("task_id", "")).strip(),
            max_rows=show_lessons,
        )
    )

    for row in events:
        tool = str(row.get("tool", ""))
        is_executor = _is_executor_tool(tool)
        if not show_all_tools and not is_executor:
            continue
        step = int(row.get("step", 0) or 0)
        ok = bool(row.get("ok", False))
        if ok and not show_ok_steps:
            continue
        state = "OK" if ok else "FAIL"
        lines.append(f"  step {step:02d} {tool} -> {state}")
        attempt = _extract_attempt_text(row.get("tool_input", {}), tool_name=tool)
        if attempt:
            if is_executor:
                lines.append("    attempt:")
                lines.extend(_format_multiline(attempt, line_prefix="      "))
            else:
                lines.append(f"    input: {_short(attempt)}")

        err = str(row.get("error", "") or "")
        if err:
            lines.append(f"    err: {_short(err)}")

        mem_rows = memory_by_step.get(step, [])
        if mem_rows:
            hard = next((item for item in mem_rows if str(item.get("channel", "")) == "hard_failure"), None)
            if hard:
                fp = str(hard.get("fingerprint", "")).strip()
                tags = hard.get("tags", [])
                tag_text = ",".join(str(tag) for tag in tags) if isinstance(tags, list) else str(tags)
                lines.append(f"    memory: hard_failure fp={fp} tags={tag_text}")
            for item in mem_rows:
                channel = str(item.get("channel", "")).strip()
                if channel in {"progress_signal", "efficiency_signal", "constraint_failure"}:
                    lines.append(f"    memory: {channel}")

        hints = _extract_hints(err, max_hints=max_hints_per_step)
        if hints:
            lines.append(f"    memory: injected_hints count={len(hints)}")
        for hint in hints:
            lines.append(f"    hint: {_short(hint, max_chars=220)}")
        if show_tool_output:
            output = str(row.get("output", "") or "").strip()
            if output:
                lines.append("    output:")
                lines.extend(_format_multiline(output, max_chars=max_output_chars, line_prefix="      "))

    v2_ratio = float(metrics.get("v2_retrieval_help_ratio", 0.0) or 0.0)
    lines.append(
        "  summary: v2_error_events={events} v2_activations={acts} v2_help_ratio={ratio:.2f} promoted={promoted} suppressed={suppressed}".format(
            events=int(metrics.get("v2_error_events", 0) or 0),
            acts=int(metrics.get("v2_lesson_activations", 0) or 0),
            ratio=v2_ratio,
            promoted=int(metrics.get("v2_promoted", 0) or 0),
            suppressed=int(metrics.get("v2_suppressed", 0) or 0),
        )
    )
    return "\n".join(lines)


def _parse_session_ids(*, session: int | None, start_session: int | None, end_session: int | None) -> list[int]:
    if session is not None:
        return [session]
    if start_session is None:
        raise ValueError("Provide --session or --start-session.")
    end_value = end_session if end_session is not None else start_session
    if end_value < start_session:
        raise ValueError("--end-session must be >= --start-session.")
    return list(range(start_session, end_value + 1))


def _render_many(
    *,
    sessions_root: Path,
    session_ids: list[int],
    max_hints_per_step: int,
    show_ok_steps: bool,
    show_all_tools: bool,
    show_tool_output: bool,
    max_output_chars: int,
    lessons_path: Path,
    show_lessons: int,
) -> str:
    blocks = [
        _render_session(
            sessions_root=sessions_root,
            session_id=session_id,
            max_hints_per_step=max_hints_per_step,
            show_ok_steps=show_ok_steps,
            show_all_tools=show_all_tools,
            show_tool_output=show_tool_output,
            max_output_chars=max_output_chars,
            lessons_path=lessons_path,
            show_lessons=show_lessons,
        )
        for session_id in session_ids
    ]
    return "\n\n" + ("\n\n".join(blocks)) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Render Memory V2 per-step timeline from session logs")
    ap.add_argument("--session", type=int, default=None, help="Single session ID (e.g. 27008)")
    ap.add_argument("--start-session", type=int, default=None, help="Range start session ID")
    ap.add_argument("--end-session", type=int, default=None, help="Range end session ID (inclusive)")
    ap.add_argument("--sessions-root", default=str(DEFAULT_SESSIONS_ROOT))
    ap.add_argument("--lessons-path", default=str(DEFAULT_LESSONS_PATH))
    ap.add_argument("--max-hints-per-step", type=int, default=4)
    ap.add_argument("--show-lessons", type=int, default=6, help="How many lesson rows to print for session domain/task")
    ap.add_argument("--show-all-tools", action="store_true", help="Include non-executor tools (show_fixture/posttask/promotion)")
    ap.add_argument("--show-tool-output", action="store_true", help="Print tool output blocks")
    ap.add_argument("--max-output-chars", type=int, default=1200)
    ap.add_argument("--show-ok-steps", action="store_true", help="Show successful executor steps too")
    ap.add_argument("--watch", action="store_true", help="Refresh timeline continuously")
    ap.add_argument("--watch-interval", type=float, default=2.0)
    args = ap.parse_args()

    try:
        session_ids = _parse_session_ids(
            session=args.session,
            start_session=args.start_session,
            end_session=args.end_session,
        )
    except ValueError as exc:
        print(str(exc))
        return 2

    sessions_root = Path(args.sessions_root)
    lessons_path = Path(args.lessons_path)
    max_hints = max(1, int(args.max_hints_per_step))

    if not args.watch:
        print(
            _render_many(
                sessions_root=sessions_root,
                session_ids=session_ids,
                max_hints_per_step=max_hints,
                show_ok_steps=bool(args.show_ok_steps),
                show_all_tools=bool(args.show_all_tools),
                show_tool_output=bool(args.show_tool_output),
                max_output_chars=max(200, int(args.max_output_chars)),
                lessons_path=lessons_path,
                show_lessons=max(0, int(args.show_lessons)),
            )
        )
        return 0

    # Watch mode intentionally stays dumb/simple for hackathon demos:
    # re-render when file signatures change and keep user in one command.
    last_signature: tuple[int, ...] | None = None
    while True:
        signature: list[int] = []
        for sid in session_ids:
            base = _session_dir(sessions_root, sid)
            for name in ("events.jsonl", "memory_events.jsonl", "metrics.json"):
                path = base / name
                signature.append(int(path.stat().st_mtime_ns) if path.exists() else -1)
                signature.append(int(path.stat().st_size) if path.exists() else -1)
        new_signature = tuple(signature)
        if new_signature != last_signature:
            print("\033[2J\033[H", end="")
            print(
                _render_many(
                    sessions_root=sessions_root,
                    session_ids=session_ids,
                    max_hints_per_step=max_hints,
                    show_ok_steps=bool(args.show_ok_steps),
                    show_all_tools=bool(args.show_all_tools),
                    show_tool_output=bool(args.show_tool_output),
                    max_output_chars=max(200, int(args.max_output_chars)),
                    lessons_path=lessons_path,
                    show_lessons=max(0, int(args.show_lessons)),
                )
            )
            last_signature = new_signature
        time.sleep(max(0.5, float(args.watch_interval)))


if __name__ == "__main__":
    raise SystemExit(main())
