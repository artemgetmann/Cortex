from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from tracks.cli_sqlite import openai_agents_sdk_transport


@dataclass(frozen=True)
class _FakeUsage:
    input_tokens: int = 11
    output_tokens: int = 7
    total_tokens: int = 18


def test_executor_transport_parses_text_and_function_calls(monkeypatch) -> None:
    state = openai_agents_sdk_transport.OpenAIAgentsSDKExecutionState(
        previous_response_id="resp_prev",
        last_source_message_count=1,
        continuation_input_items=[{"role": "user", "content": [{"type": "input_text", "text": "old"}]}],
        turns=1,
    )

    def _fake_runner_turn(**_: Any) -> openai_agents_sdk_transport._RunnerTurnResult:
        return openai_agents_sdk_transport._RunnerTurnResult(
            output_items=[
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "ok"}],
                },
                {
                    "type": "function_call",
                    "name": "run_bash",
                    "call_id": "call_1",
                    "arguments": "{\"command\": \"echo hi\"}",
                },
            ],
            usage=_FakeUsage(),
            response_id="resp_sdk_2",
            request_id="req_sdk_2",
            previous_response_id_sent="resp_prev",
            continuity_mode="delta_since_previous_response",
            input_item_count=2,
            full_input_item_count=4,
            callback_invocations=[{"tool_name": "run_bash", "tool_call_id": "call_1"}],
            continuation_input_items=[{"role": "user", "content": [{"type": "input_text", "text": "cont"}]}],
            source_message_count=3,
            tools_present=True,
            tool_choice_requested="required",
            tool_choice_effective="required",
        )

    monkeypatch.setattr(
        openai_agents_sdk_transport,
        "_run_runner_turn_via_openai_agents_sdk",
        _fake_runner_turn,
    )

    blocks, usage = openai_agents_sdk_transport.create_executor_response_via_openai_agents_sdk(
        api_key="test",
        model="gpt-5-nano",
        system_prompt="system",
        tools=[{"name": "run_bash", "description": "run bash", "input_schema": {"type": "object"}}],
        messages=[{"role": "user", "content": [{"type": "text", "text": "do it"}]}],
        execution_state=state,
    )

    assert blocks[0]["type"] == "text"
    assert blocks[0]["text"] == "ok"
    assert blocks[1]["type"] == "tool_use"
    assert blocks[1]["name"] == "run_bash"
    assert blocks[1]["id"] == "call_1"
    assert blocks[1]["input"]["command"] == "echo hi"

    assert usage["backend"] == "openai_agents_sdk"
    assert usage["api"] == "responses"
    assert usage["total_tokens"] == 18
    assert usage["continuity_mode"] == "delta_since_previous_response"
    assert usage["previous_response_id_sent"] == "resp_prev"
    assert usage["sdk_callback_invocation_count"] == 1
    assert usage["sdk_tool_choice_requested"] == "required"
    assert usage["sdk_tool_choice_effective"] == "required"
    assert usage["sdk_callback_bridge_used"] is False
    assert usage["reasoning_only_turn"] is False
    assert usage["retry_attempted"] is False
    assert usage["retry_succeeded"] is False
    assert usage["sdk_state_turns"] == 2
    assert usage["previous_response_id_next"] == "resp_sdk_2"

    assert state.turns == 2
    assert state.previous_response_id == "resp_sdk_2"
    assert state.last_source_message_count == 3


def test_executor_transport_emits_parse_warning_on_bad_arguments(monkeypatch) -> None:
    def _fake_runner_turn(**_: Any) -> openai_agents_sdk_transport._RunnerTurnResult:
        return openai_agents_sdk_transport._RunnerTurnResult(
            output_items=[
                {
                    "type": "function_call",
                    "name": "run_bash",
                    "call_id": "call_bad",
                    "arguments": "not-json",
                }
            ],
            usage=_FakeUsage(),
            response_id="resp_sdk_bad",
            request_id="req_sdk_bad",
            previous_response_id_sent="",
            continuity_mode="full_history",
            input_item_count=1,
            full_input_item_count=1,
            callback_invocations=[],
            continuation_input_items=[],
            source_message_count=0,
            tools_present=True,
            tool_choice_requested="required",
            tool_choice_effective="required",
        )

    monkeypatch.setattr(
        openai_agents_sdk_transport,
        "_run_runner_turn_via_openai_agents_sdk",
        _fake_runner_turn,
    )

    blocks, usage = openai_agents_sdk_transport.create_executor_response_via_openai_agents_sdk(
        api_key="test",
        model="gpt-5-nano",
        system_prompt="system",
        tools=[{"name": "run_bash", "description": "run bash", "input_schema": {"type": "object"}}],
        messages=[],
    )

    assert len(blocks) == 1
    assert blocks[0]["type"] == "text"
    assert "openai_agents_sdk_tool_parse_error" in blocks[0]["text"]
    assert usage["backend"] == "openai_agents_sdk"


def test_executor_transport_bridges_callback_only_turn_into_tool_use(monkeypatch) -> None:
    def _fake_runner_turn(**_: Any) -> openai_agents_sdk_transport._RunnerTurnResult:
        return openai_agents_sdk_transport._RunnerTurnResult(
            output_items=[
                {
                    "type": "reasoning",
                    "summary": [{"type": "summary_text", "text": "thinking"}],
                }
            ],
            usage=_FakeUsage(),
            response_id="resp_sdk_bridge",
            request_id="req_sdk_bridge",
            previous_response_id_sent="",
            continuity_mode="full_history",
            input_item_count=1,
            full_input_item_count=1,
            callback_invocations=[
                {
                    "tool_name": "run_bash",
                    "tool_call_id": "call_bridge_1",
                    "raw_arguments": "{\"command\": \"echo bridged\"}",
                    "parsed_input": {"command": "echo bridged"},
                }
            ],
            continuation_input_items=[],
            source_message_count=1,
            tools_present=True,
            tool_choice_requested="required",
            tool_choice_effective="required",
        )

    monkeypatch.setattr(
        openai_agents_sdk_transport,
        "_run_runner_turn_via_openai_agents_sdk",
        _fake_runner_turn,
    )

    blocks, usage = openai_agents_sdk_transport.create_executor_response_via_openai_agents_sdk(
        api_key="test",
        model="gpt-5-nano",
        system_prompt="system",
        tools=[{"name": "run_bash", "description": "run bash", "input_schema": {"type": "object"}}],
        messages=[{"role": "user", "content": [{"type": "text", "text": "do it"}]}],
    )

    assert any(block["type"] == "tool_use" for block in blocks)
    tool_use = next(block for block in blocks if block["type"] == "tool_use")
    assert tool_use["name"] == "run_bash"
    assert tool_use["id"] == "call_bridge_1"
    assert tool_use["input"]["command"] == "echo bridged"
    assert usage["sdk_callback_bridge_used"] is True
    assert usage["sdk_callback_bridge_tool_count"] >= 1
    assert usage["reasoning_only_turn"] is False


def test_build_agents_function_tools_captures_deferred_callback_output() -> None:
    class _FakeFunctionTool:
        def __init__(self, **kwargs: Any) -> None:
            self.name = kwargs["name"]
            self.description = kwargs["description"]
            self.params_json_schema = kwargs["params_json_schema"]
            self.on_invoke_tool = kwargs["on_invoke_tool"]
            self.strict_json_schema = kwargs["strict_json_schema"]

    @dataclass(frozen=True)
    class _FakeToolContext:
        tool_call_id: str = "call_1"

    callback_invocations: list[dict[str, Any]] = []
    mapped = openai_agents_sdk_transport._build_agents_function_tools(
        tools=[{"name": "run_bash", "description": "run bash", "input_schema": {"type": "object"}}],
        function_tool_cls=_FakeFunctionTool,
        callback_invocations=callback_invocations,
    )

    assert len(mapped) == 1
    result = asyncio.run(mapped[0].on_invoke_tool(_FakeToolContext(), "{\"command\": \"echo hi\"}"))
    payload = json.loads(result)

    assert payload["status"] == "deferred_to_cortex_runtime"
    assert payload["tool_name"] == "run_bash"
    assert payload["tool_call_id"] == "call_1"
    assert callback_invocations[0]["parsed_input"]["command"] == "echo hi"


def test_select_runner_input_uses_delta_with_previous_response_id() -> None:
    state = openai_agents_sdk_transport.OpenAIAgentsSDKExecutionState(
        previous_response_id="resp_1",
        last_source_message_count=1,
        turns=1,
    )
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "task"}]},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "call_1", "name": "run_bash", "input": {"command": "echo hi"}}]},
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": [{"type": "text", "text": "ok"}]}],
        },
    ]

    input_items, previous_response_id, mode, full_count = openai_agents_sdk_transport._select_runner_input(
        messages=messages,
        execution_state=state,
    )

    assert mode == "delta_since_previous_response"
    assert previous_response_id == "resp_1"
    assert len(input_items) == 1
    assert full_count >= 2


def test_executor_transport_sets_reasoning_only_diag_when_no_tool_and_retry_disabled(monkeypatch) -> None:
    monkeypatch.setenv("CORTEX_OPENAI_AGENTS_SDK_LOCAL_NO_TOOL_RETRY", "0")

    def _fake_runner_turn(**_: Any) -> openai_agents_sdk_transport._RunnerTurnResult:
        return openai_agents_sdk_transport._RunnerTurnResult(
            output_items=[{"type": "reasoning", "summary": [{"type": "summary_text", "text": "thinking"}]}],
            usage=_FakeUsage(),
            response_id="resp_sdk_reasoning_only",
            request_id="req_sdk_reasoning_only",
            previous_response_id_sent="",
            continuity_mode="full_history",
            input_item_count=1,
            full_input_item_count=1,
            callback_invocations=[],
            continuation_input_items=[],
            source_message_count=1,
            tools_present=True,
            tool_choice_requested="required",
            tool_choice_effective="required",
        )

    monkeypatch.setattr(
        openai_agents_sdk_transport,
        "_run_runner_turn_via_openai_agents_sdk",
        _fake_runner_turn,
    )

    blocks, usage = openai_agents_sdk_transport.create_executor_response_via_openai_agents_sdk(
        api_key="test",
        model="gpt-5-nano",
        system_prompt="system",
        tools=[{"name": "run_bash", "description": "run bash", "input_schema": {"type": "object"}}],
        messages=[{"role": "user", "content": [{"type": "text", "text": "do it"}]}],
    )

    assert blocks == []
    assert usage["output_tokens"] == 7
    assert usage["reasoning_only_turn"] is True
    assert usage["retry_attempted"] is False
    assert usage["retry_succeeded"] is False
    assert usage["sdk_no_tool_reason_effective"] == "reasoning_only_no_callbacks"


def test_executor_transport_resets_continuity_on_unusable_function_call(monkeypatch) -> None:
    monkeypatch.setenv("CORTEX_OPENAI_AGENTS_SDK_LOCAL_NO_TOOL_RETRY", "0")
    state = openai_agents_sdk_transport.OpenAIAgentsSDKExecutionState(
        previous_response_id="resp_prev_chain",
        last_source_message_count=1,
        continuation_input_items=[{"role": "user", "content": [{"type": "input_text", "text": "carry"}]}],
        turns=1,
    )

    def _fake_runner_turn(**_: Any) -> openai_agents_sdk_transport._RunnerTurnResult:
        return openai_agents_sdk_transport._RunnerTurnResult(
            output_items=[
                {
                    "type": "function_call",
                    "name": "run_bash",
                    "call_id": "call_bad_args",
                    # Intentionally malformed so no executable tool_use block is emitted.
                    "arguments": "{not-json",
                }
            ],
            usage=_FakeUsage(),
            response_id="resp_sdk_unusable",
            request_id="req_sdk_unusable",
            previous_response_id_sent="resp_prev_chain",
            continuity_mode="delta_since_previous_response",
            input_item_count=1,
            full_input_item_count=2,
            callback_invocations=[],
            continuation_input_items=[{"role": "assistant", "content": [{"type": "output_text", "text": "x"}]}],
            source_message_count=2,
            tools_present=True,
            tool_choice_requested="required",
            tool_choice_effective="required",
        )

    monkeypatch.setattr(
        openai_agents_sdk_transport,
        "_run_runner_turn_via_openai_agents_sdk",
        _fake_runner_turn,
    )

    blocks, usage = openai_agents_sdk_transport.create_executor_response_via_openai_agents_sdk(
        api_key="test",
        model="gpt-5-nano",
        system_prompt="system",
        tools=[{"name": "run_bash", "description": "run bash", "input_schema": {"type": "object"}}],
        messages=[{"role": "user", "content": [{"type": "text", "text": "do it"}]}],
        execution_state=state,
    )

    assert blocks and blocks[0]["type"] == "text"
    assert "openai_agents_sdk_tool_parse_error" in blocks[0]["text"]
    assert usage["reasoning_only_turn"] is False
    assert usage["sdk_no_tool_reason_effective"] == "function_call_unusable"
    assert usage["sdk_continuity_reset_due_unconsumed_function_call"] is True
    # Continuity reset must drop response-id chaining to avoid function_call_output mismatch errors.
    assert state.previous_response_id is None
    assert state.continuation_input_items == []


def test_executor_transport_sets_retry_flags_when_local_retry_recovers_tool_call(monkeypatch) -> None:
    monkeypatch.setenv("CORTEX_OPENAI_AGENTS_SDK_LOCAL_NO_TOOL_RETRY", "1")
    call_count = {"n": 0}

    def _fake_runner_turn(**_: Any) -> openai_agents_sdk_transport._RunnerTurnResult:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return openai_agents_sdk_transport._RunnerTurnResult(
                output_items=[{"type": "reasoning", "summary": [{"type": "summary_text", "text": "thinking"}]}],
                usage=_FakeUsage(),
                response_id="resp_sdk_retry_1",
                request_id="req_sdk_retry_1",
                previous_response_id_sent="",
                continuity_mode="full_history",
                input_item_count=1,
                full_input_item_count=1,
                callback_invocations=[],
                continuation_input_items=[],
                source_message_count=1,
                tools_present=True,
                tool_choice_requested="required",
                tool_choice_effective="required",
            )
        return openai_agents_sdk_transport._RunnerTurnResult(
            output_items=[
                {
                    "type": "function_call",
                    "name": "run_bash",
                    "call_id": "call_retry",
                    "arguments": "{\"command\": \"echo retried\"}",
                }
            ],
            usage=_FakeUsage(),
            response_id="resp_sdk_retry_2",
            request_id="req_sdk_retry_2",
            previous_response_id_sent="",
            continuity_mode="full_history",
            input_item_count=1,
            full_input_item_count=1,
            callback_invocations=[],
            continuation_input_items=[],
            source_message_count=1,
            tools_present=True,
            tool_choice_requested="required",
            tool_choice_effective="required",
        )

    monkeypatch.setattr(
        openai_agents_sdk_transport,
        "_run_runner_turn_via_openai_agents_sdk",
        _fake_runner_turn,
    )

    blocks, usage = openai_agents_sdk_transport.create_executor_response_via_openai_agents_sdk(
        api_key="test",
        model="gpt-5-nano",
        system_prompt="system",
        tools=[{"name": "run_bash", "description": "run bash", "input_schema": {"type": "object"}}],
        messages=[{"role": "user", "content": [{"type": "text", "text": "do it"}]}],
    )

    assert call_count["n"] == 2
    assert any(block["type"] == "tool_use" and block["id"] == "call_retry" for block in blocks)
    assert usage["reasoning_only_turn"] is False
    assert usage["retry_attempted"] is True
    assert usage["retry_succeeded"] is True


def test_compat_messages_api_returns_text_block(monkeypatch) -> None:
    def _fake_executor(**_: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return ([{"type": "text", "text": "judge output"}], {"backend": "openai_agents_sdk"})

    monkeypatch.setattr(
        openai_agents_sdk_transport,
        "create_executor_response_via_openai_agents_sdk",
        _fake_executor,
    )

    api = openai_agents_sdk_transport.OpenAIAgentsSDKCompatMessagesAPI(api_key="test")
    response = api.create(
        model="gpt-5-nano",
        system="sys",
        messages=[{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
    )
    usage = response.usage.model_dump()
    assert response.content[0].model_dump()["text"] == "judge output"
    assert usage["backend"] == "openai_agents_sdk"
