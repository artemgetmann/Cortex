from __future__ import annotations

from typing import Any


def _as_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on"}


def record_no_tool_call_event(
    *,
    metrics: dict[str, Any],
    llm_backend: str,
    last_model_response_diag: dict[str, Any] | None,
    step: int,
) -> dict[str, Any]:
    """
    Update metrics for a text-only model turn and return the canonical event payload.

    This helper isolates one fragile accounting path from `agent_cli.py` so we can:
    - keep no-tool accounting identical across backends,
    - unit test the behavior without running a full agent loop,
    - reduce accidental drift during future SDK/openai transport changes.
    """
    metrics["no_tool_call_steps"] = int(metrics.get("no_tool_call_steps", 0) or 0) + 1
    no_tool_by_backend = dict(metrics.get("no_tool_call_steps_by_backend", {}) or {})
    backend_key = str(llm_backend or "unknown").strip() or "unknown"
    no_tool_by_backend[backend_key] = int(no_tool_by_backend.get(backend_key, 0) or 0) + 1
    metrics["no_tool_call_steps_by_backend"] = no_tool_by_backend

    response_diag = dict(last_model_response_diag or {}) if isinstance(last_model_response_diag, dict) else {}
    # Keep diagnostics content-safe: booleans/counters only, never reasoning text.
    reasoning_only_turn = _as_bool(
        response_diag.get(
            "reasoning_only_turn",
            (
                _as_int(response_diag.get("function_call_count", 0), default=0) == 0
                and _as_int(response_diag.get("sdk_callback_invocation_count", 0), default=0) == 0
            ),
        )
    )
    output_tokens = max(0, _as_int(response_diag.get("output_tokens", 0), default=0))
    retry_attempted = _as_bool(
        response_diag.get(
            "retry_attempted",
            response_diag.get("sdk_local_no_tool_retry_attempted", False),
        )
    )
    retry_succeeded = _as_bool(
        response_diag.get(
            "retry_succeeded",
            response_diag.get("sdk_local_no_tool_retry_succeeded", False),
        )
    )
    failure_reason = (
        str(response_diag.get("sdk_no_tool_reason_effective", "")).strip()
        or str(response_diag.get("sdk_no_tool_reason", "")).strip()
        or ("reasoning_only_no_callbacks" if reasoning_only_turn else "no_tool_call")
    )
    failure_signature = (
        f"{backend_key}|{failure_reason}|reasoning:{int(reasoning_only_turn)}|"
        f"retry:{int(retry_attempted)}->{int(retry_succeeded)}"
    )

    previous_signature = str(metrics.get("no_tool_last_failure_signature", "")).strip()
    same_failure_streak = 1
    if failure_signature and failure_signature == previous_signature:
        same_failure_streak = int(metrics.get("no_tool_same_failure_streak", 0) or 0) + 1

    metrics["no_tool_last_failure_signature"] = failure_signature
    metrics["no_tool_same_failure_streak"] = int(max(1, same_failure_streak))
    metrics["no_tool_same_failure_streak_max"] = int(
        max(
            int(metrics.get("no_tool_same_failure_streak_max", 0) or 0),
            int(metrics["no_tool_same_failure_streak"]),
        )
    )
    if backend_key == "openai_agents_sdk":
        metrics["sdk_no_tool_same_failure_streak"] = int(metrics["no_tool_same_failure_streak"])
        metrics["sdk_no_tool_same_failure_streak_max"] = int(metrics["no_tool_same_failure_streak_max"])

    response_diag["reasoning_only_turn"] = bool(reasoning_only_turn)
    response_diag["output_tokens"] = int(output_tokens)
    response_diag["retry_attempted"] = bool(retry_attempted)
    response_diag["retry_succeeded"] = bool(retry_succeeded)
    response_diag["repeated_same_failure_streak"] = int(metrics["no_tool_same_failure_streak"])

    return {
        "step": step,
        "tool": "model_no_tool_call",
        "tool_input": {
            "backend": backend_key,
            "reasoning_only_turn": bool(reasoning_only_turn),
            "output_tokens": int(output_tokens),
            "retry_attempted": bool(retry_attempted),
            "retry_succeeded": bool(retry_succeeded),
            "repeated_same_failure_streak": int(metrics["no_tool_same_failure_streak"]),
            "response_diag": response_diag,
        },
        "ok": False,
        "error": "no_tool_call",
        "output": "",
    }


def should_inject_no_tool_recovery_prompt(
    *,
    step: int,
    max_steps: int,
    used_prompts: int,
    max_prompts: int,
) -> bool:
    """
    Decide if we should force a deterministic recovery prompt after no-tool output.

    The policy is intentionally strict and backend-agnostic:
    - never inject on/after step cap,
    - never exceed the configured retry budget.
    """
    if step >= max_steps:
        return False
    if used_prompts >= max_prompts:
        return False
    return True


def build_no_tool_recovery_prompt(*, executor_tool_name: str) -> str:
    """
    Build the exact user message used to recover from text-only turns.

    Keep this centralized so benchmark behavior is stable and diffable.
    """
    return (
        "No tool call was emitted. Do not stop. "
        f"Call exactly one tool now (`{executor_tool_name}` or a required helper tool) "
        "and continue execution."
    )
