"""LLM-based task evaluation judge.

Replaces deterministic CONTRACT.json evaluation for domains that don't have
hardcoded contracts. Uses a model one tier above the executor to judge
whether the agent completed the task correctly.

Hybrid approach: if CONTRACT.json exists and passes, skip LLM judge (saves
tokens). If it fails or doesn't exist, use LLM judge as primary signal.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


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
    raw_response: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "reasons": self.reasons,
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
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def llm_judge(
    *,
    client: Any,
    model: str,
    task_text: str,
    events: list[dict[str, Any]],
    final_state: str,
    domain_name: str,
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
        '{"passed": true|false, "score": 0.0-1.0, "reasons": ["specific reason 1", ...]}\n\n'
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
    )

    user = (
        f"TASK:\n{task_text}\n\n"
        f"EVENT LOG (last {len(compact_events)} events):\n"
        f"{json.dumps(compact_events, ensure_ascii=True, indent=1)}\n\n"
        f"FINAL STATE:\n{final_state}\n"
    )

    try:
        response = client.messages.create(
            model=model,
            max_tokens=600,
            system=system,
            messages=[{"role": "user", "content": [{"type": "text", "text": user}]}],
        )
    except Exception as exc:
        return JudgeResult(
            passed=False,
            score=0.0,
            reasons=[f"judge_call_failed: {type(exc).__name__}: {exc}"],
            raw_response="",
        )

    raw = ""
    for block in response.content:
        data = block.model_dump() if hasattr(block, "model_dump") else block
        if isinstance(data, dict) and data.get("type") == "text":
            raw += str(data.get("text", ""))

    obj = _extract_json_object(raw)
    if obj is None:
        return JudgeResult(
            passed=False,
            score=0.0,
            reasons=["judge_response_unparseable"],
            raw_response=raw[:500],
        )

    passed = bool(obj.get("passed", False))
    try:
        score = max(0.0, min(1.0, float(obj.get("score", 0.0))))
    except (TypeError, ValueError):
        score = 0.0

    reasons_raw = obj.get("reasons", [])
    reasons = [str(r).strip()[:280] for r in reasons_raw if isinstance(r, str) and str(r).strip()][:6] if isinstance(reasons_raw, list) else []

    return JudgeResult(
        passed=passed,
        score=score,
        reasons=reasons,
        raw_response=raw[:500],
    )
