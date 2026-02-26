from __future__ import annotations

from typing import Any

import pytest

from tracks.cli_sqlite import agent_cli


def _raising_stub(message: str):
    def _raise(**_: Any) -> dict[str, Any]:
        raise AssertionError(message)

    return _raise


def test_openai_executor_uses_responses_and_parses_function_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_USE_CHAT_COMPLETIONS", raising=False)
    captured: dict[str, Any] = {}

    def _fake_responses_request(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "id": "resp_123",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Running query"}],
                },
                {
                    "type": "function_call",
                    "name": "run_sqlite",
                    "arguments": '{"sql":"SELECT 1;"}',
                    "call_id": "call_abc",
                },
            ],
            "usage": {"input_tokens": 9, "output_tokens": 4},
        }

    monkeypatch.setattr(agent_cli, "_openai_responses_request", _fake_responses_request)
    monkeypatch.setattr(
        agent_cli,
        "_openai_chat_completions_request",
        _raising_stub("chat completions path should not be used when toggle is off"),
    )

    blocks, usage = agent_cli._create_executor_response_via_openai(
        api_key="test-key",
        model="gpt-5-nano",
        system_prompt="System policy",
        tools=[
            {
                "name": "run_sqlite",
                "description": "Run SQL",
                "input_schema": {
                    "type": "object",
                    "properties": {"sql": {"type": "string"}},
                    "required": ["sql"],
                },
            }
        ],
        messages=[{"role": "user", "content": [{"type": "text", "text": "execute now"}]}],
        temperature=0.0,
    )

    assert captured["instructions"] == "System policy"
    assert captured["tools"] == [
        {
            "type": "function",
            "name": "run_sqlite",
            "description": "Run SQL",
            "parameters": {
                "type": "object",
                "properties": {"sql": {"type": "string"}},
                "required": ["sql"],
            },
            "strict": True,
        }
    ]
    assert blocks == [
        {"type": "text", "text": "Running query"},
        {
            "type": "tool_use",
            "id": "call_abc",
            "name": "run_sqlite",
            "input": {"sql": "SELECT 1;"},
        },
    ]
    assert usage["backend"] == "openai"
    assert usage["api"] == "responses"
    assert usage["response_id"] == "resp_123"


def test_openai_executor_skips_malformed_function_call_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_USE_CHAT_COMPLETIONS", raising=False)
    monkeypatch.setattr(
        agent_cli,
        "_openai_responses_request",
        lambda **_: {
            "id": "resp_bad_args",
            "output": [
                {
                    "type": "function_call",
                    "name": "run_sqlite",
                    "arguments": "{\"sql\":\"SELECT 1",
                    "call_id": "call_bad",
                }
            ],
            "usage": {"input_tokens": 3, "output_tokens": 2},
        },
    )

    blocks, usage = agent_cli._create_executor_response_via_openai(
        api_key="test-key",
        model="gpt-5-nano",
        system_prompt="System policy",
        tools=[
            {
                "name": "run_sqlite",
                "description": "Run SQL",
                "input_schema": {
                    "type": "object",
                    "properties": {"sql": {"type": "string"}},
                    "required": ["sql"],
                },
            }
        ],
        messages=[{"role": "user", "content": [{"type": "text", "text": "execute now"}]}],
        temperature=0.0,
    )

    assert usage["response_id"] == "resp_bad_args"
    assert not any(block.get("type") == "tool_use" for block in blocks)
    parse_blocks = [block for block in blocks if block.get("type") == "text"]
    assert parse_blocks
    assert "openai_tool_parse_error" in str(parse_blocks[0].get("text", ""))


def test_openai_executor_respects_chat_completions_toggle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_USE_CHAT_COMPLETIONS", "1")
    captured: dict[str, Any] = {}

    def _fake_chat_request(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "id": "chat_1",
            "choices": [
                {
                    "message": {
                        "content": "Done",
                        "tool_calls": [
                            {
                                "id": "tool_call_1",
                                "function": {
                                    "name": "run_sqlite",
                                    "arguments": '{"sql":"SELECT 2;"}',
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"total_tokens": 12},
        }

    monkeypatch.setattr(agent_cli, "_openai_chat_completions_request", _fake_chat_request)
    monkeypatch.setattr(
        agent_cli,
        "_openai_responses_request",
        _raising_stub("responses path should not run when chat-completions toggle is enabled"),
    )

    blocks, usage = agent_cli._create_executor_response_via_openai(
        api_key="test-key",
        model="gpt-5-nano",
        system_prompt="System policy",
        tools=[
            {
                "name": "run_sqlite",
                "description": "Run SQL",
                "input_schema": {"type": "object"},
            }
        ],
        messages=[{"role": "user", "content": [{"type": "text", "text": "execute now"}]}],
        temperature=0.0,
    )

    assert isinstance(captured["messages"], list)
    assert blocks == [
        {"type": "text", "text": "Done"},
        {
            "type": "tool_use",
            "id": "tool_call_1",
            "name": "run_sqlite",
            "input": {"sql": "SELECT 2;"},
        },
    ]
    assert usage["backend"] == "openai"
    assert usage["api"] == "chat_completions"
    assert usage["response_id"] == "chat_1"


def test_openai_compat_messages_uses_responses_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_USE_CHAT_COMPLETIONS", raising=False)
    captured: dict[str, Any] = {}

    def _fake_responses_request(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "id": "resp_judge_1",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "All checks passed"}],
                }
            ],
            "usage": {"total_tokens": 7},
        }

    monkeypatch.setattr(agent_cli, "_openai_responses_request", _fake_responses_request)
    monkeypatch.setattr(
        agent_cli,
        "_openai_chat_completions_request",
        _raising_stub("compat path should default to responses API"),
    )

    api = agent_cli._OpenAICompatMessagesAPI(api_key="test-key")
    response = api.create(
        model="gpt-5-nano",
        max_tokens=64,
        system=[{"type": "text", "text": "Judge this output."}],
        messages=[{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
    )

    assert captured["instructions"] == "Judge this output."
    assert response.content[0].text == "All checks passed"
    usage = response.usage.model_dump()
    assert usage["backend"] == "openai"
    assert usage["api"] == "responses"
    assert usage["response_id"] == "resp_judge_1"


def test_openai_compat_messages_respects_chat_completions_toggle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_USE_CHAT_COMPLETIONS", "1")
    monkeypatch.setattr(
        agent_cli,
        "_openai_responses_request",
        _raising_stub("responses path should not be used when chat-completions toggle is enabled"),
    )
    monkeypatch.setattr(
        agent_cli,
        "_openai_chat_completions_request",
        lambda **_: {
            "id": "chat_judge_1",
            "choices": [{"message": {"content": "Legacy path"}}],
            "usage": {"total_tokens": 3},
        },
    )

    api = agent_cli._OpenAICompatMessagesAPI(api_key="test-key")
    response = api.create(
        model="gpt-5-nano",
        max_tokens=64,
        system="Judge this output.",
        messages=[{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
    )

    assert response.content[0].text == "Legacy path"
    usage = response.usage.model_dump()
    assert usage["api"] == "chat_completions"
    assert usage["response_id"] == "chat_judge_1"


def test_anthropic_messages_to_openai_responses_input_serializes_tool_history() -> None:
    input_items = agent_cli._anthropic_messages_to_openai_responses_input(
        messages=[
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Invoking tool"},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "run_sqlite",
                        "input": {"sql": "SELECT 1;"},
                    },
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_1",
                        "content": [{"type": "text", "text": "ok"}],
                    }
                ],
            },
        ]
    )

    rendered = [item["content"][0]["text"] for item in input_items]
    assert any("[tool_call id=toolu_1 name=run_sqlite]" in text for text in rendered)
    assert any("[tool_result id=toolu_1]" in text for text in rendered)
