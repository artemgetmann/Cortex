from __future__ import annotations

from typing import Any

from tracks.cli_sqlite import agent_transport_router as router


class _FakeUsage:
    def model_dump(self) -> dict[str, Any]:
        return {"input_tokens": 7}


class _FakeBlock:
    def model_dump(self) -> dict[str, Any]:
        return {"type": "text", "text": "done"}


class _FakeResponse:
    def __init__(self) -> None:
        self.usage = _FakeUsage()
        self.content = [_FakeBlock()]


class _FakeMessages:
    def __init__(self) -> None:
        self.last_request: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> _FakeResponse:
        self.last_request = dict(kwargs)
        return _FakeResponse()


class _FakeClient:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


def test_request_executor_turn_routes_anthropic() -> None:
    client = _FakeClient()

    blocks, usage = router.request_executor_turn(
        llm_backend="anthropic",
        client=client,
        openai_api_key="unused",
        model="claude-haiku-4-5",
        system_prompt="system",
        tools=[{"name": "run_sqlite"}],
        messages=[{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
        runtime_temperature=0.0,
        claude_print_fallback_model="claude-haiku-4-5",
    )

    assert blocks == [{"type": "text", "text": "done"}]
    assert usage == {"input_tokens": 7}
    assert client.messages.last_request["model"] == "claude-haiku-4-5"
    assert client.messages.last_request["temperature"] == 0.0


def test_request_executor_turn_routes_openai_with_injected_handler() -> None:
    captured: dict[str, Any] = {}

    def _fake_openai_request(**kwargs: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        captured.update(kwargs)
        return [{"type": "text", "text": "openai"}], {"backend": "openai"}

    blocks, usage = router.request_executor_turn(
        llm_backend="openai",
        client=None,
        openai_api_key="test-key",
        model="gpt-5-nano",
        system_prompt="system",
        tools=[{"name": "run_sqlite"}],
        messages=[{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
        runtime_temperature=None,
        tool_choice_override="required",
        claude_print_fallback_model="claude-haiku-4-5",
        openai_request_fn=_fake_openai_request,
    )

    assert blocks == [{"type": "text", "text": "openai"}]
    assert usage == {"backend": "openai"}
    assert captured["api_key"] == "test-key"
    assert captured["model"] == "gpt-5-nano"
    assert captured["tool_choice_override"] == "required"


def test_request_executor_turn_routes_claude_print_with_prompt_logger() -> None:
    captured: dict[str, Any] = {}
    logged: dict[str, str] = {}

    def _fake_claude_print(**kwargs: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        captured.update(kwargs)
        prompt_logger = kwargs.get("prompt_logger")
        if callable(prompt_logger):
            prompt_logger("rendered prompt")
        return [{"type": "text", "text": "claude"}], {"backend": "claude_print"}

    blocks, usage = router.request_executor_turn(
        llm_backend="claude_print",
        client=None,
        openai_api_key="unused",
        model="claude-opus-4-6",
        system_prompt="system",
        tools=[{"name": "run_bash"}],
        messages=[{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
        runtime_temperature=None,
        prompt_logger=lambda text: logged.__setitem__("prompt", text),
        claude_print_fallback_model="claude-haiku-4-5",
        claude_print_request_fn=_fake_claude_print,
    )

    assert blocks == [{"type": "text", "text": "claude"}]
    assert usage == {"backend": "claude_print"}
    assert captured["fallback_model"] == "claude-haiku-4-5"
    assert logged["prompt"] == "rendered prompt"
