from __future__ import annotations

from tracks.cli_sqlite.no_tool_call_policy import (
    build_no_tool_recovery_prompt,
    record_no_tool_call_event,
    should_inject_no_tool_recovery_prompt,
)


def test_record_no_tool_call_event_updates_metrics_and_payload() -> None:
    metrics = {
        "no_tool_call_steps": 1,
        "no_tool_call_steps_by_backend": {"openai": 1},
    }

    payload = record_no_tool_call_event(
        metrics=metrics,
        llm_backend="openai_agents_sdk",
        last_model_response_diag={"function_call_count": 0},
        step=4,
    )

    assert metrics["no_tool_call_steps"] == 2
    assert metrics["no_tool_call_steps_by_backend"]["openai"] == 1
    assert metrics["no_tool_call_steps_by_backend"]["openai_agents_sdk"] == 1
    assert payload["tool"] == "model_no_tool_call"
    assert payload["step"] == 4
    assert payload["tool_input"]["backend"] == "openai_agents_sdk"
    assert payload["tool_input"]["response_diag"]["function_call_count"] == 0
    assert payload["error"] == "no_tool_call"


def test_should_inject_no_tool_recovery_prompt_respects_caps() -> None:
    assert should_inject_no_tool_recovery_prompt(step=2, max_steps=6, used_prompts=0, max_prompts=3) is True
    assert should_inject_no_tool_recovery_prompt(step=6, max_steps=6, used_prompts=0, max_prompts=3) is False
    assert should_inject_no_tool_recovery_prompt(step=2, max_steps=6, used_prompts=3, max_prompts=3) is False


def test_build_no_tool_recovery_prompt_mentions_executor_tool() -> None:
    prompt = build_no_tool_recovery_prompt(executor_tool_name="run_bash")
    assert "No tool call was emitted" in prompt
    assert "run_bash" in prompt
    assert "Call exactly one tool now" in prompt

