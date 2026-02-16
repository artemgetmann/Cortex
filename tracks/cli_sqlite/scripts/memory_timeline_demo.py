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


def _first_present(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any | None:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _to_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            rows.append(text)
    return rows


def _as_str_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    rows: dict[str, str] = {}
    for key, raw_value in value.items():
        k = str(key).strip()
        v = str(raw_value).strip()
        if not k or not v:
            continue
        rows[k] = v
    return rows


def _try_parse_json_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    text = raw.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _candidate_payloads_for_step(row: dict[str, Any], mem_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Build a tolerant payload list for observability parsing.

    Session artifacts changed multiple times during the hackathon, so injected
    lessons and retrieval diagnostics may appear in different nested keys. We
    collect several likely containers and parse them uniformly.
    """
    payloads: list[dict[str, Any]] = []
    for candidate in (
        row,
        row.get("tool_input"),
        row.get("memory_v2"),
        row.get("memory"),
        row.get("v2"),
        _try_parse_json_dict(row.get("output")),
    ):
        parsed = _as_dict(candidate)
        if not parsed:
            continue
        payloads.append(parsed)
        for nested_key in ("result", "memory_v2", "memory", "v2", "retrieval", "diagnostics"):
            nested = _as_dict(parsed.get(nested_key))
            if nested:
                payloads.append(nested)
    for mem_row in mem_rows:
        payloads.append(mem_row)
        metadata = _as_dict(mem_row.get("metadata"))
        if metadata:
            payloads.append(metadata)
    return payloads


def _collect_injected_step_payload(
    *,
    row: dict[str, Any],
    mem_rows: list[dict[str, Any]],
    max_hints: int,
) -> dict[str, Any]:
    hints: list[str] = []
    lesson_ids: list[str] = []
    hint_lanes: dict[str, str] = {}
    lesson_lanes: dict[str, str] = {}

    err = str(row.get("error", "") or "")
    for hint in _extract_hints(err, max_hints=max_hints):
        if hint and hint not in hints:
            hints.append(hint)

    for payload in _candidate_payloads_for_step(row, mem_rows):
        injected_lists = []
        for key in ("injected_lessons", "on_error_injected_lessons", "injected_hints", "hints"):
            injected_lists.extend(_as_list(payload.get(key)))
        for item in injected_lists:
            if isinstance(item, str):
                text = item.strip()
                if text and text not in hints and len(hints) < max_hints:
                    hints.append(text)
                continue
            if not isinstance(item, dict):
                continue
            lane = str(_first_present(item, ("lane", "source_lane", "retrieval_lane")) or "").strip()
            text = str(
                _first_present(
                    item,
                    ("rule_text", "hint", "text", "lesson", "message"),
                )
                or ""
            ).strip()
            if text and text not in hints and len(hints) < max_hints:
                hints.append(text)
            if text and lane and text not in hint_lanes:
                hint_lanes[text] = lane
            lesson_id = str(_first_present(item, ("lesson_id", "id")) or "").strip()
            if lesson_id and lesson_id not in lesson_ids:
                lesson_ids.append(lesson_id)
            if lesson_id and lane and lesson_id not in lesson_lanes:
                lesson_lanes[lesson_id] = lane

        for key in ("lesson_ids", "injected_lesson_ids", "v2_lesson_ids"):
            for lesson_id in _as_str_list(payload.get(key)):
                if lesson_id not in lesson_ids:
                    lesson_ids.append(lesson_id)
        for key in ("lesson_lanes", "injected_lesson_lanes", "lane_by_lesson_id"):
            for lesson_id, lane in _as_str_dict(payload.get(key)).items():
                if lesson_id not in lesson_lanes:
                    lesson_lanes[lesson_id] = lane
        for key in ("hint_lanes", "injected_hint_lanes", "lane_by_hint"):
            for hint_text, lane in _as_str_dict(payload.get(key)).items():
                if hint_text not in hint_lanes:
                    hint_lanes[hint_text] = lane

    return {
        "hints": hints[:max_hints],
        "lesson_ids": lesson_ids,
        "hint_lanes": hint_lanes,
        "lesson_lanes": lesson_lanes,
    }


def _collect_retrieval_scores(
    *,
    row: dict[str, Any],
    mem_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    score_rows: list[dict[str, Any]] = []
    for payload in _candidate_payloads_for_step(row, mem_rows):
        raw_rows: list[Any] = []
        for key in (
            "retrieval_scores",
            "retrieval_score_breakdown",
            "score_breakdown",
            "v2_retrieval_scores",
        ):
            raw_rows.extend(_as_list(payload.get(key)))
        for item in raw_rows:
            item_dict = _as_dict(item)
            if not item_dict:
                continue
            score_dict = _as_dict(item_dict.get("score"))
            lesson_dict = _as_dict(item_dict.get("lesson"))
            lesson_id = str(
                _first_present(
                    item_dict,
                    ("lesson_id", "id"),
                )
                or _first_present(score_dict, ("lesson_id",))
                or _first_present(lesson_dict, ("lesson_id", "id"))
                or ""
            ).strip()
            raw_total = _first_present(item_dict, ("score_total", "total_score", "score"))
            total = _to_float(raw_total)
            if total is None and isinstance(raw_total, dict):
                total = _to_float(raw_total.get("score"))
            if total is None:
                total = _to_float(score_dict.get("score"))
            if total is None:
                continue
            normalized = {
                "lesson_id": lesson_id,
                "score": total,
                "lane": str(
                    _first_present(item_dict, ("lane", "source_lane", "retrieval_lane"))
                    or _first_present(lesson_dict, ("lane", "source_lane"))
                    or _first_present(score_dict, ("lane", "source_lane"))
                    or ""
                ).strip(),
                "fingerprint_match": _to_float(_first_present(item_dict, ("fingerprint_match",)) or score_dict.get("fingerprint_match")),
                "tag_overlap": _to_float(_first_present(item_dict, ("tag_overlap",)) or score_dict.get("tag_overlap")),
                "text_similarity": _to_float(_first_present(item_dict, ("text_similarity",)) or score_dict.get("text_similarity")),
                "reliability": _to_float(_first_present(item_dict, ("reliability",)) or score_dict.get("reliability")),
                "recency": _to_float(_first_present(item_dict, ("recency",)) or score_dict.get("recency")),
            }
            score_rows.append(normalized)
    return score_rows


def _render_v2_observability_sections(
    *,
    metrics: dict[str, Any],
    events: list[dict[str, Any]],
    memory_by_step: dict[int, list[dict[str, Any]]],
    max_hints_per_step: int,
) -> tuple[list[str], dict[int, dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    lines: list[str] = []
    injected_by_step: dict[int, dict[str, Any]] = {}
    score_by_step: dict[int, list[dict[str, Any]]] = {}

    prerun_ids = _as_str_list(
        _first_present(metrics, ("v2_prerun_lesson_ids", "prerun_lesson_ids", "memory_prerun_lesson_ids"))
    )
    prerun_loaded = _to_int(
        _first_present(metrics, ("v2_lessons_loaded", "prerun_lessons_loaded")),
        default=len(prerun_ids),
    )
    lines.append("  memory_v2_preloaded_lessons:")
    lines.append(f"    count={prerun_loaded}")
    if prerun_ids:
        lines.append(f"    lesson_ids={','.join(prerun_ids)}")
    else:
        lines.append("    lesson_ids=(none)")

    for row in events:
        step = _to_int(row.get("step"), default=-1)
        if step < 0:
            continue
        tool = str(row.get("tool", "")).strip()
        if not _is_executor_tool(tool):
            continue
        if bool(row.get("ok", False)):
            continue
        mem_rows = memory_by_step.get(step, [])
        injected = _collect_injected_step_payload(row=row, mem_rows=mem_rows, max_hints=max_hints_per_step)
        if injected.get("hints") or injected.get("lesson_ids"):
            injected_by_step[step] = injected
        scores = _collect_retrieval_scores(row=row, mem_rows=mem_rows)
        if scores:
            score_by_step[step] = scores

    lines.append("  memory_v2_on_error_injected_lessons:")
    if not injected_by_step:
        lines.append("    (none)")
    else:
        for step in sorted(injected_by_step):
            row = injected_by_step[step]
            hints = _as_list(row.get("hints"))
            lesson_ids = _as_str_list(row.get("lesson_ids"))
            hint_lanes = _as_str_dict(row.get("hint_lanes"))
            lesson_lanes = _as_str_dict(row.get("lesson_lanes"))
            lane_values = sorted({lane for lane in [*hint_lanes.values(), *lesson_lanes.values()] if lane})
            lines.append(
                "    step {step:02d}: hints={hints_count} lesson_ids={id_count}{lane_suffix}".format(
                    step=step,
                    hints_count=len(hints),
                    id_count=len(lesson_ids),
                    lane_suffix=(f" lanes={','.join(lane_values)}" if lane_values else ""),
                )
            )
            if lesson_ids:
                lesson_tokens: list[str] = []
                for lesson_id in lesson_ids:
                    lane = lesson_lanes.get(lesson_id, "").strip()
                    lesson_tokens.append(f"{lesson_id}({lane})" if lane else lesson_id)
                lines.append(f"      ids={','.join(lesson_tokens)}")
            for hint in hints:
                hint_text = str(hint)
                lane = hint_lanes.get(hint_text, "").strip()
                lane_prefix = f"[{lane}] " if lane else ""
                lines.append(f"      hint={lane_prefix}{_short(hint_text, max_chars=220)}")

    lines.append("  memory_v2_retrieval_score_breakdown:")
    if not score_by_step:
        lines.append("    (unavailable)")
    else:
        for step in sorted(score_by_step):
            lines.append(f"    step {step:02d}:")
            for score in score_by_step[step]:
                lesson_id = str(score.get("lesson_id", "")).strip() or "unknown"
                score_text = f"{float(score.get('score', 0.0) or 0.0):.3f}"
                parts = [
                    f"total={score_text}",
                ]
                lane = str(score.get("lane", "") or "").strip()
                if lane:
                    parts.append(f"lane={lane}")
                for key in ("fingerprint_match", "tag_overlap", "text_similarity", "reliability", "recency"):
                    value = score.get(key)
                    if isinstance(value, (int, float)):
                        parts.append(f"{key}={float(value):.3f}")
                lines.append(f"      lesson={lesson_id} " + " ".join(parts))

    return lines, injected_by_step, score_by_step


def _is_executor_tool(name: str) -> bool:
    lowered = str(name).strip().lower()
    return lowered in {"run_gridtool", "run_fluxtool", "run_sqlite", "run_artic", "run_bash"}


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
    observability_lines, injected_by_step, _ = _render_v2_observability_sections(
        metrics=metrics,
        events=events,
        memory_by_step=memory_by_step,
        max_hints_per_step=max_hints_per_step,
    )
    lines.extend(observability_lines)

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

        injected = injected_by_step.get(step, {})
        hints = _as_str_list(injected.get("hints"))
        hint_lanes = _as_str_dict(injected.get("hint_lanes"))
        if not hints:
            hints = _extract_hints(err, max_hints=max_hints_per_step)
        if hints:
            lines.append(f"    memory: injected_hints count={len(hints)}")
        lesson_ids = _as_str_list(injected.get("lesson_ids"))
        lesson_lanes = _as_str_dict(injected.get("lesson_lanes"))
        if lesson_ids:
            lesson_tokens: list[str] = []
            for lesson_id in lesson_ids:
                lane = lesson_lanes.get(lesson_id, "").strip()
                lesson_tokens.append(f"{lesson_id}({lane})" if lane else lesson_id)
            lines.append(f"    memory: injected_lesson_ids={','.join(lesson_tokens)}")
        for hint in hints:
            lane = hint_lanes.get(hint, "").strip()
            lane_prefix = f"[{lane}] " if lane else ""
            lines.append(f"    hint: {lane_prefix}{_short(hint, max_chars=220)}")
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
