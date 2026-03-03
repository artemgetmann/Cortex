from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

from claude_print_runtime import clip_text, extract_first_json_object
from tracks.cli_sqlite.openai_transport import (
    _extract_system_prompt_text,
    anthropic_messages_to_openai_responses_input,
)


@dataclass
class OpenAIAgentsSDKExecutionState:
    """
    Mutable per-run state for SDK runner continuity.

    The CLI loop is still the source of truth for tool execution/memory writes.
    We only keep the minimum state needed to continue runner turns efficiently.
    """

    previous_response_id: str | None = None
    last_source_message_count: int = 0
    continuation_input_items: list[dict[str, Any]] = field(default_factory=list)
    turns: int = 0


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


@dataclass(frozen=True)
class _RunnerTurnResult:
    output_items: list[Any]
    usage: Any
    response_id: str
    request_id: str
    previous_response_id_sent: str
    continuity_mode: str
    input_item_count: int
    full_input_item_count: int
    callback_invocations: list[dict[str, Any]]
    continuation_input_items: list[dict[str, Any]]
    source_message_count: int
    tools_present: bool
    tool_choice_requested: str
    tool_choice_effective: str


def _load_openai_agents_sdk() -> tuple[Any, Any, Any, Any, Any, Any, Any]:
    """
    Lazy-load SDK modules so default OpenAI/Anthropic paths do not require
    extra dependencies.
    """
    try:
        from agents import Agent, RunConfig, Runner
        from agents.model_settings import ModelSettings
        from agents.models.openai_responses import OpenAIResponsesModel
        from agents.tool import FunctionTool
        from openai import AsyncOpenAI
    except Exception as exc:  # pragma: no cover - depends on optional runtime deps
        raise RuntimeError(
            "OpenAI Agents SDK backend requires optional deps. "
            "Install with: pip install openai-agents openai"
        ) from exc
    return Runner, Agent, RunConfig, OpenAIResponsesModel, ModelSettings, FunctionTool, AsyncOpenAI


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


def _tool_choice_policy(*, execution_context: bool) -> str:
    """
    Runtime policy for SDK tool selection.

    Safety policy:
    - Execution context may enforce tools for deterministic benchmark behavior.
    - Non-execution/chat context defaults to auto.
    """
    default_policy = "required" if execution_context else "auto"
    raw = str(os.getenv("CORTEX_OPENAI_AGENTS_SDK_TOOL_CHOICE", default_policy)).strip().lower()
    if raw in {"none", "off"}:
        return "none"
    if raw in {"auto", "required"}:
        return raw
    return default_policy


def _tool_call_enforcement_prefix() -> str:
    return (
        "TOOL EXECUTION POLICY: When function tools are available, you must call a tool. "
        "Do not stop with text-only output until at least one function call is emitted in this turn."
    )


def _int_env(name: str, default: int) -> int:
    raw = str(os.getenv(name, str(default))).strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


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


def _json_roundtrip(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=True))
    except Exception:
        return value


def _clone_input_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cloned: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        copied = _json_roundtrip(item)
        if isinstance(copied, dict):
            cloned.append(copied)
    return cloned


def _tool_result_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return str(content or "").strip()
    parts: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = str(part.get("type", "")).strip().lower()
        if part_type == "text":
            text = str(part.get("text", "")).strip()
            if text:
                parts.append(text)
        elif part_type == "image":
            parts.append("[image omitted]")
    return "\n".join(parts).strip()


def _anthropic_messages_to_runner_input_items(
    *,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Convert Anthropic-style messages into runner input items with structured
    function_call_output items for tool results.
    """
    input_items: list[dict[str, Any]] = []

    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role", "")).strip().lower()
        content = message.get("content", [])
        if not isinstance(content, list):
            content = [{"type": "text", "text": str(content or "")}]

        text_parts: list[str] = []

        def _flush_text_parts() -> None:
            merged = "\n".join(part for part in text_parts if part).strip()
            text_parts.clear()
            if not merged:
                return
            input_items.append(
                {
                    "role": "user" if role not in {"assistant", "system"} else role,
                    "content": [{"type": "input_text", "text": merged}],
                }
            )

        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type", "")).strip().lower()
            if block_type == "text":
                text = str(block.get("text", "")).strip()
                if text:
                    text_parts.append(text)
                continue
            if not (role == "user" and block_type == "tool_result"):
                continue
            _flush_text_parts()
            tool_use_id = str(block.get("tool_use_id", "")).strip()
            if not tool_use_id:
                continue
            tool_text = _tool_result_content_to_text(block.get("content"))
            if bool(block.get("is_error", False)):
                tool_text = f"[tool_error] {tool_text}".strip()
            if not tool_text:
                tool_text = "(empty tool result)"
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": tool_use_id,
                    "output": tool_text,
                }
            )

        _flush_text_parts()

    return input_items


def _build_agents_function_tools(
    *,
    tools: list[dict[str, Any]],
    function_tool_cls: Any,
    callback_invocations: list[dict[str, Any]],
) -> list[Any]:
    """
    Build SDK FunctionTool entries from Anthropic-style tool specs.

    Callback behavior:
    - Capture tool-call metadata from Runner output.
    - Return a deterministic deferred payload so the existing Cortex loop can
      execute tools and keep memory/metrics semantics unchanged.
    """
    mapped: list[Any] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name", "")).strip()
        if not name:
            continue

        async def _on_invoke_tool(tool_context: Any, raw_arguments: str, *, tool_name: str = name) -> str:
            parsed_input, parse_warning = _decode_tool_arguments(raw_arguments, tool_name=tool_name)
            callback_entry: dict[str, Any] = {
                "tool_name": tool_name,
                "tool_call_id": str(getattr(tool_context, "tool_call_id", "")).strip(),
                "raw_arguments": str(raw_arguments or ""),
                "parsed_input": parsed_input,
            }
            if parse_warning:
                callback_entry["parse_warning"] = parse_warning
            callback_invocations.append(callback_entry)

            payload: dict[str, Any] = {
                "status": "deferred_to_cortex_runtime",
                "tool_name": tool_name,
                "tool_call_id": callback_entry["tool_call_id"],
            }
            if parsed_input is not None:
                payload["input"] = parsed_input
            if parse_warning:
                payload["parse_warning"] = parse_warning
            return json.dumps(payload, ensure_ascii=True, sort_keys=True)

        mapped.append(
            function_tool_cls(
                name=name,
                description=str(tool.get("description", "")).strip(),
                params_json_schema=tool.get("input_schema", {}),
                on_invoke_tool=_on_invoke_tool,
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
            raise RuntimeError(
                f"OpenAI Agents SDK requested unknown tool '{tool_name}'. Allowed: {sorted(allowed_tool_names)}"
            )
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


def _callback_invocations_to_assistant_blocks(
    *,
    callback_invocations: list[dict[str, Any]],
    allowed_tool_names: set[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Bridge SDK callback traces into Anthropic-style tool_use blocks.

    Why this exists:
    - Some SDK turns can invoke tool callbacks while raw output items are
      reasoning-only (no function_call item exposed in the final payload).
    - The Cortex runtime expects explicit tool_use blocks. Without this bridge,
      those turns look like text-only stalls.
    """
    bridged_blocks: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen_call_ids: set[str] = set()
    for idx, row in enumerate(callback_invocations):
        if not isinstance(row, dict):
            continue
        tool_name = str(row.get("tool_name", "")).strip()
        if not tool_name or tool_name not in allowed_tool_names:
            continue
        parsed_input = row.get("parsed_input")
        parse_warning = str(row.get("parse_warning", "")).strip()
        if not isinstance(parsed_input, dict):
            parsed_input, parse_warning_retry = _decode_tool_arguments(
                row.get("raw_arguments", "{}"),
                tool_name=tool_name,
            )
            if parse_warning_retry:
                parse_warning = parse_warning_retry
        if parse_warning:
            warnings.append(parse_warning)
        if not isinstance(parsed_input, dict):
            # Keep going so one malformed callback does not hide valid ones.
            continue
        call_id = str(row.get("tool_call_id", "")).strip() or f"toolu_openai_sdk_cb_{uuid.uuid4().hex[:12]}_{idx}"
        if call_id in seen_call_ids:
            continue
        seen_call_ids.add(call_id)
        bridged_blocks.append(
            {
                "type": "tool_use",
                "id": call_id,
                "name": tool_name,
                "input": parsed_input,
            }
        )
    return bridged_blocks, warnings


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


def _output_item_diagnostics(output_items: list[Any]) -> dict[str, Any]:
    """
    Build compact diagnostics for SDK response shape.

    This helps debug early-stop behavior where model returns text-only output.
    """
    type_counts: dict[str, int] = {}
    function_call_count = 0
    text_block_count = 0
    for item in output_items:
        payload = _item_to_dict(item)
        item_type = str(payload.get("type", "")).strip().lower() or "unknown"
        type_counts[item_type] = int(type_counts.get(item_type, 0)) + 1
        if item_type == "function_call":
            function_call_count += 1
        if item_type == "message":
            content = payload.get("content", [])
            if isinstance(content, list):
                for block in content:
                    block_payload = _item_to_dict(block)
                    block_type = str(block_payload.get("type", "")).strip().lower()
                    if block_type in {"output_text", "text"}:
                        text_block_count += 1
    return {
        "output_item_count": len(output_items),
        "output_item_type_counts": type_counts,
        "function_call_count": function_call_count,
        "text_block_count": text_block_count,
    }


def _extract_delta_messages_for_continuation(
    *,
    messages: list[dict[str, Any]],
    execution_state: OpenAIAgentsSDKExecutionState,
) -> list[dict[str, Any]]:
    if execution_state.last_source_message_count < 0:
        execution_state.last_source_message_count = 0
    if execution_state.last_source_message_count > len(messages):
        execution_state.last_source_message_count = 0
        execution_state.previous_response_id = None
        execution_state.continuation_input_items = []
        return list(messages)

    delta_messages = list(messages[execution_state.last_source_message_count :])
    while delta_messages:
        head = delta_messages[0]
        if not isinstance(head, dict):
            break
        if str(head.get("role", "")).strip().lower() != "assistant":
            break
        delta_messages.pop(0)
    return delta_messages


def _select_runner_input(
    *,
    messages: list[dict[str, Any]],
    execution_state: OpenAIAgentsSDKExecutionState | None,
) -> tuple[list[dict[str, Any]], str | None, str, int]:
    full_input_items = anthropic_messages_to_openai_responses_input(messages=messages)
    if execution_state is None or execution_state.turns <= 0:
        return full_input_items, None, "full_history", len(full_input_items)

    delta_messages = _extract_delta_messages_for_continuation(messages=messages, execution_state=execution_state)
    delta_items = _anthropic_messages_to_runner_input_items(messages=delta_messages)

    if execution_state.previous_response_id and delta_items:
        return (
            delta_items,
            execution_state.previous_response_id,
            "delta_since_previous_response",
            len(full_input_items),
        )

    if execution_state.continuation_input_items and delta_items:
        merged = [*execution_state.continuation_input_items, *delta_items]
        return merged, None, "to_input_list_continuation", len(full_input_items)

    return full_input_items, None, "full_history_fallback", len(full_input_items)


def _run_runner_turn_via_openai_agents_sdk(
    *,
    api_key: str,
    model: str,
    system_prompt: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    max_tokens: int,
    temperature: float | None,
    execution_state: OpenAIAgentsSDKExecutionState | None,
    execution_context: bool,
) -> _RunnerTurnResult:
    (
        runner_cls,
        agent_cls,
        run_config_cls,
        openai_responses_model_cls,
        model_settings_cls,
        function_tool_cls,
        async_openai_cls,
    ) = _load_openai_agents_sdk()

    callback_invocations: list[dict[str, Any]] = []
    source_message_count = len(messages)
    input_items, previous_response_id, continuity_mode, full_input_count = _select_runner_input(
        messages=messages,
        execution_state=execution_state,
    )

    async def _do_call() -> Any:
        client = async_openai_cls(
            api_key=api_key,
            base_url=_openai_base_url(),
            timeout=_openai_timeout_seconds(),
        )
        model_obj = openai_responses_model_cls(model=model, openai_client=client)
        sdk_tools = _build_agents_function_tools(
            tools=tools,
            function_tool_cls=function_tool_cls,
            callback_invocations=callback_invocations,
        )
        tools_present = bool(sdk_tools)
        tool_choice_policy = _tool_choice_policy(execution_context=execution_context)
        tool_choice_effective = "none"
        model_settings_kwargs: dict[str, Any] = {
            "max_tokens": max(0, int(max_tokens)),
            "parallel_tool_calls": False,
        }
        if tools_present and tool_choice_policy in {"auto", "required"}:
            model_settings_kwargs["tool_choice"] = tool_choice_policy
            tool_choice_effective = tool_choice_policy
        if temperature is not None and _should_send_temperature(model=model):
            model_settings_kwargs["temperature"] = float(temperature)
        try:
            model_settings = model_settings_cls(**model_settings_kwargs)
        except TypeError:
            # Backward-compatible fallback for SDK versions without `tool_choice`.
            model_settings_kwargs.pop("tool_choice", None)
            if tools_present and tool_choice_policy in {"auto", "required"}:
                tool_choice_effective = "unsupported_by_sdk"
            model_settings = model_settings_cls(**model_settings_kwargs)

        system_instructions = _extract_system_prompt_text(system_prompt)
        if tools_present and execution_context and tool_choice_policy in {"auto", "required"}:
            system_instructions = f"{_tool_call_enforcement_prefix()}\n\n{system_instructions}".strip()

        agent = agent_cls(
            name="cortex_executor",
            instructions=system_instructions,
            model=model_obj,
            tools=sdk_tools,
            model_settings=model_settings,
            tool_use_behavior="stop_on_first_tool",
        )
        run_config = run_config_cls(
            tracing_disabled=True,
            model_settings=model_settings,
        )
        return await runner_cls.run(
            agent,
            input=input_items,
            max_turns=1,
            run_config=run_config,
            previous_response_id=previous_response_id,
        ), tools_present, tool_choice_policy, tool_choice_effective

    run_result, tools_present, tool_choice_requested, tool_choice_effective = _run_async(_do_call())
    raw_responses = list(getattr(run_result, "raw_responses", []) or [])
    if not raw_responses:
        raise RuntimeError("OpenAI Agents SDK runner returned no raw responses.")
    model_response = raw_responses[-1]
    output_items = list(getattr(model_response, "output", []) or [])
    response_id = str(getattr(model_response, "response_id", "")).strip()
    request_id = str(getattr(model_response, "request_id", "")).strip()

    to_input_items: list[dict[str, Any]] = []
    to_input_list_fn = getattr(run_result, "to_input_list", None)
    if callable(to_input_list_fn):
        try:
            raw_items = to_input_list_fn()
            if isinstance(raw_items, list):
                for item in raw_items:
                    if isinstance(item, dict):
                        to_input_items.append(_json_roundtrip(item))
        except Exception:
            to_input_items = []

    return _RunnerTurnResult(
        output_items=output_items,
        usage=getattr(model_response, "usage", None),
        response_id=response_id,
        request_id=request_id,
        previous_response_id_sent=str(previous_response_id or ""),
        continuity_mode=continuity_mode,
        input_item_count=len(input_items),
        full_input_item_count=full_input_count,
        callback_invocations=_clone_input_items(callback_invocations),
        continuation_input_items=to_input_items,
        source_message_count=source_message_count,
        tools_present=bool(tools_present),
        tool_choice_requested=str(tool_choice_requested or ""),
        tool_choice_effective=str(tool_choice_effective or ""),
    )


def create_executor_response_via_openai_agents_sdk(
    *,
    api_key: str,
    model: str,
    system_prompt: str,
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    temperature: float | None = None,
    execution_state: OpenAIAgentsSDKExecutionState | None = None,
    execution_context: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    def _blocks_from_turn_result(
        result: _RunnerTurnResult,
    ) -> tuple[list[dict[str, Any]], bool, int]:
        local_output_items = list(result.output_items)
        local_assistant_blocks = _response_output_items_to_assistant_blocks(
            output_items=local_output_items,
            allowed_tool_names=allowed_tool_names,
        )
        local_has_tool_use = any(
            isinstance(block, dict) and str(block.get("type", "")).strip().lower() == "tool_use"
            for block in local_assistant_blocks
        )
        local_bridge_used = False
        if not local_has_tool_use and result.callback_invocations:
            bridged_blocks, bridge_warnings = _callback_invocations_to_assistant_blocks(
                callback_invocations=result.callback_invocations,
                allowed_tool_names=allowed_tool_names,
            )
            if bridge_warnings:
                local_assistant_blocks.insert(0, {"type": "text", "text": "\n".join(bridge_warnings)})
            if bridged_blocks:
                local_bridge_used = True
                local_assistant_blocks.extend(bridged_blocks)
                local_has_tool_use = True
        return local_assistant_blocks, local_bridge_used, len(local_output_items)

    turn_result = _run_runner_turn_via_openai_agents_sdk(
        api_key=api_key,
        model=model,
        system_prompt=system_prompt,
        messages=messages,
        tools=tools,
        max_tokens=_int_env("CORTEX_OPENAI_AGENTS_SDK_MAX_TOKENS", 1800),
        temperature=temperature,
        execution_state=execution_state,
        execution_context=execution_context,
    )
    output_items = list(turn_result.output_items)
    allowed_tool_names = {
        str(tool.get("name", "")).strip()
        for tool in tools
        if isinstance(tool, dict) and str(tool.get("name", "")).strip()
    }
    assistant_blocks, callback_bridge_used, output_item_count = _blocks_from_turn_result(turn_result)

    no_tool_candidate = (
        bool(execution_context)
        and bool(turn_result.tools_present)
        and int(_output_item_diagnostics(output_items).get("function_call_count", 0) or 0) == 0
        and int(len(turn_result.callback_invocations)) == 0
        and not any(
            isinstance(block, dict) and str(block.get("type", "")).strip().lower() == "tool_use"
            for block in assistant_blocks
        )
    )
    local_retry_enabled = str(os.getenv("CORTEX_OPENAI_AGENTS_SDK_LOCAL_NO_TOOL_RETRY", "1")).strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
    }
    local_retry_attempted = False
    local_retry_succeeded = False
    local_retry_error = ""
    local_retry_forced_full_history = False
    if no_tool_candidate and local_retry_enabled:
        local_retry_attempted = True
        local_retry_forced_full_history = True
        try:
            retry_result = _run_runner_turn_via_openai_agents_sdk(
                api_key=api_key,
                model=model,
                system_prompt=system_prompt,
                messages=messages,
                tools=tools,
                max_tokens=_int_env("CORTEX_OPENAI_AGENTS_SDK_LOCAL_NO_TOOL_RETRY_MAX_TOKENS", 3600),
                temperature=temperature,
                execution_state=None,
                execution_context=execution_context,
            )
            retry_blocks, retry_bridge_used, retry_output_count = _blocks_from_turn_result(retry_result)
            retry_has_tool = any(
                isinstance(block, dict) and str(block.get("type", "")).strip().lower() == "tool_use"
                for block in retry_blocks
            )
            if retry_has_tool:
                turn_result = retry_result
                output_items = list(turn_result.output_items)
                assistant_blocks = retry_blocks
                callback_bridge_used = retry_bridge_used
                output_item_count = retry_output_count
                local_retry_succeeded = True
        except Exception as exc:
            local_retry_error = f"{type(exc).__name__}:{exc}"

    if execution_state is not None:
        execution_state.turns = int(execution_state.turns) + 1
        execution_state.last_source_message_count = int(turn_result.source_message_count)
        execution_state.continuation_input_items = _clone_input_items(turn_result.continuation_input_items)
        execution_state.previous_response_id = turn_result.response_id or None

    usage_payload = _coerce_usage_payload(
        usage=turn_result.usage,
        model=model,
        response_id=turn_result.response_id,
        request_id=turn_result.request_id,
    )
    usage_payload.update(_output_item_diagnostics(output_items))
    usage_payload.update(
        {
            "continuity_mode": turn_result.continuity_mode,
            "previous_response_id_sent": turn_result.previous_response_id_sent,
            "sdk_input_item_count": int(turn_result.input_item_count),
            "sdk_full_history_item_count": int(turn_result.full_input_item_count),
            "sdk_callback_invocation_count": len(turn_result.callback_invocations),
            "sdk_callback_tool_names": sorted(
                {
                    str(row.get("tool_name", "")).strip()
                    for row in turn_result.callback_invocations
                    if isinstance(row, dict)
                }
                - {""}
            ),
            "sdk_tools_present": bool(turn_result.tools_present),
            "sdk_tool_choice_requested": str(turn_result.tool_choice_requested or ""),
            "sdk_tool_choice_effective": str(turn_result.tool_choice_effective or ""),
            "sdk_max_tokens_requested": _int_env("CORTEX_OPENAI_AGENTS_SDK_MAX_TOKENS", 1800),
            "sdk_local_retry_max_tokens_requested": _int_env(
                "CORTEX_OPENAI_AGENTS_SDK_LOCAL_NO_TOOL_RETRY_MAX_TOKENS",
                3600,
            ),
            "sdk_callback_bridge_used": bool(callback_bridge_used),
            "sdk_callback_bridge_tool_count": int(
                sum(
                    1
                    for block in assistant_blocks
                    if isinstance(block, dict) and str(block.get("type", "")).strip().lower() == "tool_use"
                )
            ),
            "sdk_tool_enforcement_prefix_applied": bool(
                turn_result.tools_present and execution_context and turn_result.tool_choice_requested in {"auto", "required"}
            ),
            "sdk_no_tool_candidate": bool(no_tool_candidate),
            "sdk_no_tool_reason": (
                "reasoning_only_no_callbacks"
                if no_tool_candidate
                else ""
            ),
            "sdk_local_no_tool_retry_attempted": bool(local_retry_attempted),
            "sdk_local_no_tool_retry_succeeded": bool(local_retry_succeeded),
            "sdk_local_no_tool_retry_error": str(local_retry_error or ""),
            "sdk_local_no_tool_retry_forced_full_history": bool(local_retry_forced_full_history),
            "sdk_output_item_count_effective": int(output_item_count),
        }
    )
    if execution_state is not None:
        usage_payload["previous_response_id_next"] = str(execution_state.previous_response_id or "")
        usage_payload["sdk_state_turns"] = int(execution_state.turns)
        usage_payload["sdk_state_message_cursor"] = int(execution_state.last_source_message_count)
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
            execution_state=None,
            execution_context=False,
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
