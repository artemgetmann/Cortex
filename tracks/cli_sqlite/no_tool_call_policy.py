from __future__ import annotations

from typing import Any


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
    return {
        "step": step,
        "tool": "model_no_tool_call",
        "tool_input": {
            "backend": backend_key,
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

