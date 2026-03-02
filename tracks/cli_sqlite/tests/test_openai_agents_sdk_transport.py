from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tracks.cli_sqlite import openai_agents_sdk_transport


@dataclass(frozen=True)
class _FakeUsage:
    input_tokens: int = 11
    output_tokens: int = 7
    total_tokens: int = 18


@dataclass(frozen=True)
class _FakeModelResponse:
    output: list[dict[str, Any]]
    usage: _FakeUsage
    response_id: str = "resp_sdk_1"
    request_id: str = "req_sdk_1"


def test_executor_transport_parses_text_and_function_calls(
    monkeypatch,
) -> None:
    def _fake_fetch(**_: Any) -> _FakeModelResponse:
        return _FakeModelResponse(
            output=[
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
        )

    monkeypatch.setattr(
        openai_agents_sdk_transport,
        "_fetch_model_response_via_openai_agents_sdk",
        _fake_fetch,
    )

    blocks, usage = openai_agents_sdk_transport.create_executor_response_via_openai_agents_sdk(
        api_key="test",
        model="gpt-5-nano",
        system_prompt="system",
        tools=[{"name": "run_bash", "description": "run bash", "input_schema": {"type": "object"}}],
        messages=[{"role": "user", "content": [{"type": "text", "text": "do it"}]}],
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


def test_executor_transport_emits_parse_warning_on_bad_arguments(monkeypatch) -> None:
    def _fake_fetch(**_: Any) -> _FakeModelResponse:
        return _FakeModelResponse(
            output=[
                {
                    "type": "function_call",
                    "name": "run_bash",
                    "call_id": "call_bad",
                    "arguments": "not-json",
                }
            ],
            usage=_FakeUsage(),
        )

    monkeypatch.setattr(
        openai_agents_sdk_transport,
        "_fetch_model_response_via_openai_agents_sdk",
        _fake_fetch,
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
