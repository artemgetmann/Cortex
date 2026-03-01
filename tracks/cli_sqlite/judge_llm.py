"""LLM-based task evaluation judge.

Replaces deterministic CONTRACT.json evaluation for domains that don't have
hardcoded contracts. Uses a model one tier above the executor to judge
whether the agent completed the task correctly.

Hybrid approach: if CONTRACT.json exists and passes, skip LLM judge (saves
tokens). If it fails or doesn't exist, use LLM judge as primary signal.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable


JUDGE_TIER_MAP = {
    "haiku": "claude-sonnet-4-5",
    "sonnet": "claude-opus-4-6",
    "opus": "claude-opus-4-6",
}


@dataclass(frozen=True)
class JudgeResult:
    passed: bool
    score: float
    reasons: list[str]
    doc_grounding: list[dict[str, str]] = field(default_factory=list)
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "reasons": self.reasons,
            "doc_grounding": self.doc_grounding,
        }


def default_judge_model(executor_model: str) -> str:
    """Return judge model one tier above executor."""
    lowered = executor_model.lower()
    if "opus" in lowered:
        return JUDGE_TIER_MAP["opus"]
    if "sonnet" in lowered:
        return JUDGE_TIER_MAP["sonnet"]
    return JUDGE_TIER_MAP["haiku"]


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Prefer fenced JSON blocks when present.
    for fenced in re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.IGNORECASE | re.DOTALL):
        try:
            parsed = json.loads(fenced)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    # Fallback: scan for the first balanced JSON object and parse candidates.
    n = len(text)
    for start in (i for i, ch in enumerate(text) if ch == "{"):
        depth = 0
        in_string = False
        escape = False
        for idx in range(start, n):
            ch = text[idx]
            if in_string:
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                continue
            if ch == "{":
                depth += 1
                continue
            if ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : idx + 1]
                    try:
                        parsed = json.loads(candidate)
                    except json.JSONDecodeError:
                        break
                    if isinstance(parsed, dict):
                        return parsed
                    break
    return None


def _extract_partial_json_fields(raw: str) -> dict[str, Any] | None:
    """
    Best-effort parser for truncated judge output.

    Why this exists:
    - some model responses are cut before the closing brace
    - strict JSON parse then fails even when key fields are present
    - this fallback recovers only explicit fields (`passed`, `score`,
      and quoted reason strings) and never invents values
    """

    text = str(raw or "")
    if not text.strip():
        return None

    passed_match = re.search(r'"passed"\s*:\s*(true|false)', text, flags=re.IGNORECASE)
    score_match = re.search(r'"score"\s*:\s*(-?\d+(?:\.\d+)?)', text, flags=re.IGNORECASE)
    reasons: list[str] = []
    reasons_start = re.search(r'"reasons"\s*:\s*\[', text, flags=re.IGNORECASE)
    if reasons_start:
        # Restrict parsing to the reasons array segment only. Previous
        # implementation scanned the remainder of the payload and accidentally
        # captured keys from sibling objects (for example doc_grounding keys).
        blob = text[reasons_start.end() :]
        segment_chars: list[str] = []
        depth = 1
        in_string = False
        escape = False
        closed = False
        for ch in blob:
            if in_string:
                segment_chars.append(ch)
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                segment_chars.append(ch)
                continue
            if ch == "[":
                depth += 1
                segment_chars.append(ch)
                continue
            if ch == "]":
                depth -= 1
                if depth == 0:
                    closed = True
                    break
                segment_chars.append(ch)
                continue
            segment_chars.append(ch)

        segment = "".join(segment_chars)
        if not closed:
            # Truncated payload fallback: cut at the first sibling key marker.
            sibling_key = re.search(
                r',\s*"(?:doc_grounding|passed|score|raw_response|notes|meta)"\s*:',
                segment,
                flags=re.IGNORECASE,
            )
            if sibling_key:
                segment = segment[: sibling_key.start()]

        for match in re.finditer(r'"([^"\\]*(?:\\.[^"\\]*)*)"', segment):
            value = bytes(match.group(1), "utf-8").decode("unicode_escape")
            cleaned = str(value).strip()
            if cleaned:
                reasons.append(cleaned)
            if len(reasons) >= 8:
                break

    if not passed_match and not score_match and not reasons:
        return None

    payload: dict[str, Any] = {}
    if passed_match:
        payload["passed"] = str(passed_match.group(1)).lower() == "true"
    if score_match:
        try:
            payload["score"] = float(score_match.group(1))
        except ValueError:
            payload["score"] = 0.0
    if reasons:
        payload["reasons"] = reasons
    payload["doc_grounding"] = []
    return payload


def llm_judge(
    *,
    client: Any,
    model: str,
    task_text: str,
    events: list[dict[str, Any]],
    final_state: str,
    domain_name: str,
    docs_context: str = "",
    temperature: float | None = None,
    input_logger: Callable[[dict[str, Any]], None] | None = None,
) -> JudgeResult:
    """Evaluate task completion using an LLM judge.

    Args:
        client: anthropic.Anthropic instance.
        model: Judge model ID (should be one tier above executor).
        task_text: What the agent was supposed to do.
        events: Agent event log (tool calls + results).
        final_state: Domain-specific state capture (DB dump, file output, etc).
        domain_name: Domain identifier ("sqlite", "gridtool", etc).

    Returns:
        JudgeResult with pass/fail, score, and reasons.
    """
    # Take last 30 events to keep context manageable
    tail_events = events[-30:]
    # Strip large outputs to save tokens
    compact_events = []
    for evt in tail_events:
        row: dict[str, Any] = {
            "step": evt.get("step"),
            "tool": evt.get("tool"),
            "ok": evt.get("ok"),
        }
        tool_input = evt.get("tool_input", {})
        if isinstance(tool_input, dict):
            row["tool_input"] = {k: (v[:300] + "..." if isinstance(v, str) and len(v) > 300 else v) for k, v in tool_input.items()}
        error = evt.get("error")
        if error:
            row["error"] = str(error)[:500]
        output = evt.get("output")
        if output:
            row["output"] = str(output)[:500]
        compact_events.append(row)

    system = (
        "You are a strict task evaluator for a self-improving AI agent system.\n"
        f"Domain: {domain_name}\n\n"
        "Your job: judge whether the agent completed the assigned task correctly.\n\n"
        "Return STRICT JSON only:\n"
        '{"passed": true|false, "score": 0.0-1.0, "reasons": ["specific reason 1", ...], '
        '"doc_grounding": [{"source_id":"...","note":"..."}]}\n\n'
        "Scoring guide:\n"
        "- 1.0: Task fully completed, correct output\n"
        "- 0.75: Task mostly complete, minor issues\n"
        "- 0.5: Partial completion, significant issues\n"
        "- 0.25: Attempted but largely wrong\n"
        "- 0.0: Did not complete or completely wrong\n\n"
        "Rules:\n"
        "- Each reason MUST reference concrete evidence: error messages, wrong output, missing steps, or specific tool call results.\n"
        "- Do NOT give generic reasons like 'good job' or 'needs improvement'.\n"
        "- Judge based on the TASK REQUIREMENTS, not on style or approach.\n"
        "- If the final state shows correct results, the task passes regardless of how many errors occurred along the way.\n"
        "- If documentation context is supplied, cite it in doc_grounding when used.\n"
        "\n"
        "Visual evidence guidance:\n"
        "- UI-heavy demos (FL Studio/computer-use) include explicit zoom and screenshot expectations. Track every zoom action and screenshot entry in the event log and cite those that align with the expected success image before you score.\n"
        "- When the task or final state references a `success_image`, `failure_image`, or named zoom region, validate that the recorded image metadata matches the claimed outcome, and explain how it satisfies or violates the success criteria. Treat missing or mismatched images as concrete failures.\n"
        "- Deduct score or mark failure if the agent skips the required zoom/screenshot checkpoint yet still claims success. Mention repeated zooms without decisive clicks as evidence of indecision, or missing screenshots as missing evidence.\n"
    )

    user = (
        f"TASK:\n{task_text}\n\n"
        f"EVENT LOG (last {len(compact_events)} events):\n"
        f"{json.dumps(compact_events, ensure_ascii=True, indent=1)}\n\n"
        f"FINAL STATE:\n{final_state}\n\n"
        f"DOCUMENTATION CONTEXT (may be empty):\n{docs_context}\n"
    )
    if input_logger is not None:
        input_logger(
            {
                "model": model,
                "domain_name": domain_name,
                "task_text": task_text,
                "system_prompt": system,
                "user_payload": user,
                "events_compact": compact_events,
                "final_state": final_state,
                "docs_context": docs_context,
            }
        )

    try:
        request: dict[str, Any] = {
            "model": model,
            "max_tokens": 600,
            "system": system,
            "messages": [{"role": "user", "content": [{"type": "text", "text": user}]}],
        }
        if temperature is not None:
            request["temperature"] = float(temperature)
        response = client.messages.create(
            **request,
        )
    except Exception as exc:
        return JudgeResult(
            passed=False,
            score=0.0,
            reasons=[f"judge_call_failed: {type(exc).__name__}: {exc}"],
            doc_grounding=[],
            raw_response="",
        )

    raw = ""
    for block in response.content:
        data = block.model_dump() if hasattr(block, "model_dump") else block
        if isinstance(data, dict) and data.get("type") == "text":
            raw += str(data.get("text", ""))

    obj = _extract_json_object(raw)
    if obj is None:
        obj = _extract_partial_json_fields(raw)
    if obj is None:
        return JudgeResult(
            passed=False,
            score=0.0,
            reasons=["judge_response_unparseable"],
            doc_grounding=[],
            raw_response=raw[:500],
        )

    passed = bool(obj.get("passed", False))
    try:
        score = max(0.0, min(1.0, float(obj.get("score", 0.0))))
    except (TypeError, ValueError):
        score = 0.0

    reasons_raw = obj.get("reasons", [])
    reasons = [str(r).strip()[:280] for r in reasons_raw if isinstance(r, str) and str(r).strip()][:6] if isinstance(reasons_raw, list) else []
    grounding_rows: list[dict[str, str]] = []
    grounding_raw = obj.get("doc_grounding", [])
    if isinstance(grounding_raw, list):
        for row in grounding_raw[:12]:
            if not isinstance(row, dict):
                continue
            source_id = str(row.get("source_id", "")).strip()
            note = str(row.get("note", "")).strip()
            if not source_id and not note:
                continue
            grounding_rows.append(
                {
                    "source_id": source_id[:120],
                    "note": note[:240],
                }
            )

    return JudgeResult(
        passed=passed,
        score=score,
        reasons=reasons,
        doc_grounding=grounding_rows,
        raw_response=raw[:500],
    )
