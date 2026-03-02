from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass
from typing import Any

from claude_print_runtime import clip_text, extract_first_json_object
from tracks.cli_sqlite.openai_transport import (
    _extract_system_prompt_text,
    anthropic_messages_to_openai_responses_input,
)


@dataclass(frozen=True)
class _OpenAIAgentsSDKUsageWrapper:
    payload: dict[str, Any]

    def model_dump(self) -> dict[str, Any]:
        return dict(self.payload)


@dataclass(frozen=True)
class _OpenAIAgentsSDKTextBlock:
    text: str

    def model_dump(self) -> dict[str, Any]:
        return {"type": "text", "text": self.text}


@dataclass(frozen=True)
class _OpenAIAgentsSDKCompatResponse:
    content: list[_OpenAIAgentsSDKTextBlock]
    usage: _OpenAIAgentsSDKUsageWrapper


def _load_openai_agents_sdk() -> tuple[Any, Any, Any, Any, Any]:
    """
    Lazy-load SDK modules so default OpenAI/Anthropic paths do not require
    extra dependencies.
    """
    try:
        from agents.model_settings import ModelSettings
        from agents.models.interface import ModelTracing
        from agents.models.openai_responses import OpenAIResponsesModel
        from agents.tool import FunctionTool
        from openai import AsyncOpenAI
    except Exception as exc:  # pragma: no cover - depends on optional runtime deps
        raise RuntimeError(
            "OpenAI Agents SDK backend requires optional deps. "
            "Install with: pip install openai-agents openai"
        ) from exc
    return OpenAIResponsesModel, ModelSettings, ModelTracing, FunctionTool, AsyncOpenAI


def _openai_base_url() -> str:
    base_url = str(os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).strip().rstrip("/")
    if not base_url:
        return "https://api.openai.com/v1"
    return base_url


def _openai_timeout_seconds() -> float:
    try:
        return float(os.getenv("OPENAI_TIMEOUT_S", "120"))
    except ValueError:
        return 120.0


def _should_send_temperature(*, model: str) -> bool:
    """
    GPT-5 Responses models reject `temperature`.
    Keep this disabled by default, with an env override for experiments.
    """
    if str(os.getenv("OPENAI_AGENTS_SDK_USE_TEMPERATURE", "")).strip().lower() in {"1", "true", "yes", "on"}:
        return True
    model_name = str(model or "").strip().lower()
    if model_name.startswith("gpt-5"):
        return False
    return False


def _run_async(coro: Any) -> Any:
    """
    Execute SDK async calls from the sync runtime loop.

    The runtime is usually sync; this helper keeps async complexity localized.
    """
    try:
        return asyncio.run(coro)
    except RuntimeError as exc:
        # Defensive fallback for environments already running an event loop.
        if "asyncio.run() cannot be called from a running event loop" not in str(exc):
            raise
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def _build_agents_function_tools(
    *,
    tools: list[dict[str, Any]],
    function_tool_cls: Any,
) -> list[Any]:
    """
    Build SDK FunctionTool entries from Anthropic-style tool specs.

    Tool execution stays in the existing Cortex loop; SDK tool callbacks are
    placeholders and should never execute in this transport mode.
    """

    async def _noop_on_invoke(_: Any, __: str) -> str:
        return "Tool execution is managed by Cortex runtime loop."

    mapped: list[Any] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name", "")).strip()
        if not name:
            continue
        mapped.append(
            function_tool_cls(
                name=name,
                description=str(tool.get("description", "")).strip(),
                params_json_schema=tool.get("input_schema", {}),
                on_invoke_tool=_noop_on_invoke,
                strict_json_schema=True,
            )
        )
    return mapped


def _item_to_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return dict(item)
    model_dump = getattr(item, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            return {}
    return {}


def _response_output_items_to_assistant_blocks(
    *,
    output_items: list[Any],
    allowed_tool_names: set[str],
) -> list[dict[str, Any]]:
    """
    Normalize SDK response output into Anthropic-style blocks consumed by
    existing Cortex loops (`text` + `tool_use`).
    """
    assistant_blocks: list[dict[str, Any]] = []
    text_parts: list[str] = []

    def _decode_tool_arguments(raw_arguments: Any, *, tool_name: str) -> tuple[dict[str, Any] | None, str | None]:
        if isinstance(raw_arguments, dict):
            return raw_arguments, None
        raw_text = str(raw_arguments or "").strip() or "{}"
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            try:
                parsed = extract_first_json_object(raw_text)
            except Exception:
                clipped = clip_text(raw_text, max_chars=500)
                return None, (
                    f"[openai_agents_sdk_tool_parse_error] function_call '{tool_name}' "
                    f"arguments were not valid JSON and were skipped: {clipped}"
                )
        if not isinstance(parsed, dict):
            return None, (
                f"[openai_agents_sdk_tool_parse_error] function_call '{tool_name}' "
                "arguments decoded to non-object and were skipped."
            )
        return parsed, None

    for idx, item in enumerate(output_items):
        payload = _item_to_dict(item)
        item_type = str(payload.get("type", "")).strip().lower()
        if item_type == "message":
            content = payload.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                block_payload = _item_to_dict(block)
                block_type = str(block_payload.get("type", "")).strip().lower()
                if block_type not in {"output_text", "text"}:
                    continue
                text_value = block_payload.get("text", "")
                if isinstance(text_value, dict):
                    text = str(text_value.get("value", "")).strip()
                else:
                    text = str(text_value).strip()
                if text:
                    text_parts.append(text)
            continue

        if item_type != "function_call":
            continue
        tool_name = str(payload.get("name", "")).strip()
        if not tool_name:
            raise RuntimeError(f"OpenAI Agents SDK function_call at index {idx} missing name.")
        if tool_name not in allowed_tool_names:
            raise RuntimeError(f"OpenAI Agents SDK requested unknown tool '{tool_name}'. Allowed: {sorted(allowed_tool_names)}")
        tool_input, parse_warning = _decode_tool_arguments(payload.get("arguments", "{}"), tool_name=tool_name)
        if parse_warning:
            text_parts.append(parse_warning)
            continue
        if tool_input is None:
            continue
        call_id = str(payload.get("call_id", "")).strip() or f"toolu_openai_sdk_{uuid.uuid4().hex[:12]}_{idx}"
        assistant_blocks.append({"type": "tool_use", "id": call_id, "name": tool_name, "input": tool_input})

    merged_text = "\n".join(part for part in text_parts if part).strip()
    if merged_text:
        assistant_blocks.insert(0, {"type": "text", "text": merged_text})
    return assistant_blocks


def _coerce_usage_payload(*, usage: Any, model: str, response_id: str, request_id: str) -> dict[str, Any]:
    return {
        "backend": "openai_agents_sdk",
        "model": model,
        "response_id": response_id,
        "request_id": request_id,
        "api": "responses",
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
    }


def _fetch_model_response_via_openai_agents_sdk(
    *,
    api_key: str,
    model: str,
    system_prompt: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    max_tokens: int,
    temperature: float | None,
) -> Any:
    """
    One model turn through OpenAI Agents SDK Responses model.

    We intentionally call the model layer (not full Runner) so Cortex retains
    control over tool execution, retries, and memory instrumentation.
    """
    (
        openai_responses_model_cls,
        model_settings_cls,
        model_tracing_cls,
        function_tool_cls,
        async_openai_cls,
    ) = _load_openai_agents_sdk()

    async def _do_call() -> Any:
        client = async_openai_cls(
            api_key=api_key,
            base_url=_openai_base_url(),
            timeout=_openai_timeout_seconds(),
        )
        model_obj = openai_responses_model_cls(model=model, openai_client=client)
        model_settings_kwargs: dict[str, Any] = {
            "max_tokens": max(0, int(max_tokens)),
            "parallel_tool_calls": False,
        }
        if temperature is not None and _should_send_temperature(model=model):
            model_settings_kwargs["temperature"] = float(temperature)
        model_settings = model_settings_cls(**model_settings_kwargs)
        input_items = anthropic_messages_to_openai_responses_input(messages=messages)
        sdk_tools = _build_agents_function_tools(tools=tools, function_tool_cls=function_tool_cls)
        return await model_obj.get_response(
            system_instructions=_extract_system_prompt_text(system_prompt),
            input=input_items,
            model_settings=model_settings,
            tools=sdk_tools,
            output_schema=None,
            handoffs=[],
            tracing=model_tracing_cls.DISABLED,
            previous_response_id=None,
            conversation_id=None,
            prompt=None,
        )

    return _run_async(_do_call())


def create_executor_response_via_openai_agents_sdk(
    *,
    api_key: str,
    model: str,
    system_prompt: str,
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    temperature: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    model_response = _fetch_model_response_via_openai_agents_sdk(
        api_key=api_key,
        model=model,
        system_prompt=system_prompt,
        messages=messages,
        tools=tools,
        max_tokens=1800,
        temperature=temperature,
    )
    output_items = list(getattr(model_response, "output", []) or [])
    allowed_tool_names = {
        str(tool.get("name", "")).strip()
        for tool in tools
        if isinstance(tool, dict) and str(tool.get("name", "")).strip()
    }
    assistant_blocks = _response_output_items_to_assistant_blocks(
        output_items=output_items,
        allowed_tool_names=allowed_tool_names,
    )
    usage_payload = _coerce_usage_payload(
        usage=getattr(model_response, "usage", None),
        model=model,
        response_id=str(getattr(model_response, "response_id", "")).strip(),
        request_id=str(getattr(model_response, "request_id", "")).strip(),
    )
    return assistant_blocks, usage_payload


class OpenAIAgentsSDKCompatMessagesAPI:
    """
    Anthropic-like `.messages.create(...)` shim over OpenAI Agents SDK.

    Judge + lesson generation paths already speak Anthropic-style `.messages`
    contract. This keeps those callsites unchanged.
    """

    def __init__(self, *, api_key: str) -> None:
        self._api_key = api_key

    def create(
        self,
        *,
        model: str,
        max_tokens: int = 0,
        system: Any = "",
        messages: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        **_: Any,
    ) -> _OpenAIAgentsSDKCompatResponse:
        assistant_blocks, usage = create_executor_response_via_openai_agents_sdk(
            api_key=self._api_key,
            model=model,
            system_prompt=_extract_system_prompt_text(system),
            tools=[],
            messages=messages or [],
            temperature=temperature,
        )
        # Judge/lesson calls are text-only; preserve text while ignoring
        # accidental tool blocks if they ever appear.
        text_parts = [
            str(block.get("text", "")).strip()
            for block in assistant_blocks
            if isinstance(block, dict) and str(block.get("type", "")).strip().lower() == "text"
        ]
        merged_text = "\n".join(part for part in text_parts if part).strip()
        if not merged_text:
            merged_text = "(empty response)"
        usage_payload = dict(usage)
        if int(max_tokens) > 0:
            usage_payload["max_tokens_requested"] = int(max_tokens)
        return _OpenAIAgentsSDKCompatResponse(
            content=[_OpenAIAgentsSDKTextBlock(text=merged_text)],
            usage=_OpenAIAgentsSDKUsageWrapper(payload=usage_payload),
        )


class OpenAIAgentsSDKCompatClient:
    def __init__(self, *, api_key: str) -> None:
        self.messages = OpenAIAgentsSDKCompatMessagesAPI(api_key=api_key)
