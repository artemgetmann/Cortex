from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any

from claude_print_runtime import clip_text, extract_first_json_object


def _extract_system_prompt_text(system: Any) -> str:
    """Normalize Anthropic-style system blocks into plain text for OpenAI APIs."""
    if isinstance(system, str):
        return system.strip()
    if isinstance(system, list):
        parts: list[str] = []
        for block in system:
            if not isinstance(block, dict):
                continue
            if str(block.get("type", "")).strip().lower() != "text":
                continue
            text = str(block.get("text", "")).strip()
            if text:
                parts.append(text)
        return "\n\n".join(parts).strip()
    return str(system or "").strip()


def _tool_result_content_to_text(content: Any) -> str:
    """Flatten Anthropic tool_result content blocks to plain text."""
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
            # OpenAI tool role content is text-only; keep signal without payload.
            parts.append("[image omitted]")
    return "\n".join(parts).strip()


def _openai_message_content_to_text(content: Any) -> str:
    """Best-effort text extraction from OpenAI/Anthropic message content shapes."""
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return str(content or "").strip()
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            text = item.strip()
            if text:
                parts.append(text)
            continue
        if not isinstance(item, dict):
            continue
        text_field = item.get("text")
        if isinstance(text_field, str):
            text = text_field.strip()
            if text:
                parts.append(text)
            continue
        if isinstance(text_field, dict):
            value = str(text_field.get("value", "")).strip()
            if value:
                parts.append(value)
            continue
        value = str(item.get("content", "")).strip()
        if value:
            parts.append(value)
    return "\n".join(parts).strip()


def _anthropic_user_blocks_to_openai_messages(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Anthropic user/tool_result blocks into OpenAI chat-style messages."""
    messages: list[dict[str, Any]] = []
    pending_text: list[str] = []

    def _flush_pending_text() -> None:
        if not pending_text:
            return
        merged = "\n".join(part for part in pending_text if part).strip()
        pending_text.clear()
        if merged:
            messages.append({"role": "user", "content": merged})

    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type", "")).strip().lower()
        if block_type == "text":
            text = str(block.get("text", "")).strip()
            if text:
                pending_text.append(text)
            continue
        if block_type != "tool_result":
            continue
        _flush_pending_text()
        tool_call_id = str(block.get("tool_use_id", "")).strip()
        if not tool_call_id:
            continue
        tool_text = _tool_result_content_to_text(block.get("content"))
        if bool(block.get("is_error", False)):
            tool_text = f"[tool_error] {tool_text}".strip()
        if not tool_text:
            tool_text = "(empty tool result)"
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": tool_text,
            }
        )

    _flush_pending_text()
    return messages


def _anthropic_assistant_blocks_to_openai_message(blocks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Convert Anthropic assistant blocks to one OpenAI assistant message."""
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for idx, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type", "")).strip().lower()
        if block_type == "text":
            text = str(block.get("text", "")).strip()
            if text:
                text_parts.append(text)
            continue
        if block_type != "tool_use":
            continue
        tool_name = str(block.get("name", "")).strip()
        if not tool_name:
            continue
        tool_input = block.get("input", {})
        if not isinstance(tool_input, dict):
            tool_input = {}
        tool_call_id = str(block.get("id", "")).strip() or f"toolu_openai_{uuid.uuid4().hex[:12]}_{idx}"
        tool_calls.append(
            {
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(tool_input, ensure_ascii=True, sort_keys=True),
                },
            }
        )
    if not text_parts and not tool_calls:
        return None
    message: dict[str, Any] = {"role": "assistant", "content": "\n".join(text_parts).strip()}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return message


def _anthropic_messages_to_openai_messages(
    *,
    messages: list[dict[str, Any]],
    system_prompt: str,
) -> list[dict[str, Any]]:
    """Convert Anthropic-style message history into OpenAI chat-completions shape."""
    converted: list[dict[str, Any]] = []
    system_text = str(system_prompt or "").strip()
    if system_text:
        converted.append({"role": "system", "content": system_text})
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", "")).strip().lower()
        content = msg.get("content")
        if not isinstance(content, list):
            text = str(content or "").strip()
            if text:
                converted.append({"role": role or "user", "content": text})
            continue
        if role == "assistant":
            assistant_message = _anthropic_assistant_blocks_to_openai_message(content)
            if assistant_message is not None:
                converted.append(assistant_message)
            continue
        converted.extend(_anthropic_user_blocks_to_openai_messages(content))
    return converted


def _anthropic_tools_to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map Anthropic tool schemas to OpenAI chat-completions tools."""
    converted: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name", "")).strip()
        if not name:
            continue
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": str(tool.get("description", "")).strip(),
                    "parameters": tool.get("input_schema", {}),
                },
            }
        )
    return converted


def _openai_use_chat_completions() -> bool:
    """Responses-first policy; chat-completions only when explicitly allowed."""
    allow_fallback = str(os.getenv("OPENAI_ALLOW_CHAT_COMPLETIONS_FALLBACK", "")).strip().lower()
    if allow_fallback in {"1", "true", "yes", "on"}:
        return True
    # Backward-compatible legacy toggle.
    legacy = str(os.getenv("OPENAI_USE_CHAT_COMPLETIONS", "")).strip().lower()
    return legacy in {"1", "true", "yes", "on"}


def _openai_base_url() -> str:
    base_url = str(os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).strip().rstrip("/")
    if not base_url:
        return "https://api.openai.com/v1"
    return base_url


def anthropic_messages_to_openai_responses_input(
    *,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Convert Anthropic-style history into Responses API input items.

    Tool calls/results are serialized as plain text to stay compatible with
    OpenAI-compatible providers that differ on function_call_output schema.
    """
    converted = _anthropic_messages_to_openai_messages(messages=messages, system_prompt="")
    input_items: list[dict[str, Any]] = []
    for msg in converted:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", "")).strip().lower()
        if role in {"system", "user", "assistant"}:
            content_text = _openai_message_content_to_text(msg.get("content"))
            if role == "assistant":
                tool_calls = msg.get("tool_calls", [])
                if isinstance(tool_calls, list):
                    for call in tool_calls:
                        if not isinstance(call, dict):
                            continue
                        function = call.get("function", {})
                        if not isinstance(function, dict):
                            continue
                        tool_name = str(function.get("name", "")).strip()
                        raw_arguments = str(function.get("arguments", "")).strip()
                        call_id = str(call.get("id", "")).strip()
                        if not tool_name:
                            continue
                        call_line = f"[tool_call id={call_id or 'unknown'} name={tool_name}] {raw_arguments or '{}'}"
                        content_text = f"{content_text}\n{call_line}".strip() if content_text else call_line
            if not content_text:
                continue
            content_type = "output_text" if role == "assistant" else "input_text"
            input_items.append(
                {
                    "role": role,
                    "content": [{"type": content_type, "text": content_text}],
                }
            )
            continue
        if role != "tool":
            continue
        tool_call_id = str(msg.get("tool_call_id", "")).strip() or "unknown"
        tool_content = _openai_message_content_to_text(msg.get("content"))
        if not tool_content:
            tool_content = "(empty tool result)"
        input_items.append(
            {
                "role": "user",
                "content": [{"type": "input_text", "text": f"[tool_result id={tool_call_id}]\n{tool_content}"}],
            }
        )
    return input_items


def _anthropic_tools_to_openai_responses_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map Anthropic tool schemas to Responses API tools."""
    converted: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name", "")).strip()
        if not name:
            continue
        converted.append(
            {
                "type": "function",
                "name": name,
                "description": str(tool.get("description", "")).strip(),
                "parameters": tool.get("input_schema", {}),
                "strict": True,
            }
        )
    return converted


def _openai_responses_output_to_text(payload: dict[str, Any]) -> str:
    """Extract assistant text from Responses API payload."""
    output_text = str(payload.get("output_text", "")).strip()
    if output_text:
        return output_text
    output_items = payload.get("output", [])
    if not isinstance(output_items, list):
        return ""
    parts: list[str] = []
    for item in output_items:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type", "")).strip().lower()
        if item_type == "message":
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = str(block.get("type", "")).strip().lower()
                if block_type in {"output_text", "text"}:
                    text_value = block.get("text", "")
                    if isinstance(text_value, dict):
                        text = str(text_value.get("value", "")).strip()
                    else:
                        text = str(text_value).strip()
                    if text:
                        parts.append(text)
        elif item_type in {"output_text", "text"}:
            text = str(item.get("text", "")).strip()
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def openai_responses_request(
    *,
    api_key: str,
    model: str,
    input_items: list[dict[str, Any]],
    instructions: str,
    tools: list[dict[str, Any]] | None,
    max_tokens: int,
    temperature: float | None,
) -> dict[str, Any]:
    """Call Responses API with conservative fallback over optional fields."""
    url = f"{_openai_base_url()}/responses"
    base_payload: dict[str, Any] = {"model": model, "input": input_items}
    instructions_text = str(instructions or "").strip()
    if instructions_text:
        base_payload["instructions"] = instructions_text
    if tools:
        base_payload["tools"] = tools
        base_payload["tool_choice"] = "auto"
    if int(max_tokens) > 0:
        base_payload["max_output_tokens"] = int(max_tokens)
    reasoning_effort = str(os.getenv("OPENAI_RESPONSES_REASONING_EFFORT", "low")).strip().lower()
    if reasoning_effort in {"low", "medium", "high"}:
        base_payload["reasoning"] = {"effort": reasoning_effort}
    text_verbosity = str(os.getenv("OPENAI_RESPONSES_TEXT_VERBOSITY", "low")).strip().lower()
    if text_verbosity in {"low", "medium", "high"}:
        base_payload["text"] = {"verbosity": text_verbosity}
    if temperature is not None:
        base_payload["temperature"] = float(temperature)

    temperature_options: list[float | None] = [None]
    if temperature is not None:
        temperature_options = [float(temperature), None]

    last_error: Exception | None = None
    tuning_attempts = [(True, True), (True, False), (False, False)]
    for include_reasoning, include_text in tuning_attempts:
        for maybe_temperature in temperature_options:
            payload = dict(base_payload)
            if maybe_temperature is None:
                payload.pop("temperature", None)
            else:
                payload["temperature"] = maybe_temperature
            if not include_reasoning:
                payload.pop("reasoning", None)
            if not include_text:
                payload.pop("text", None)
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            request = urllib.request.Request(url=url, data=body, method="POST")
            request.add_header("Authorization", f"Bearer {api_key}")
            request.add_header("Content-Type", "application/json")
            request.add_header("Accept", "application/json")
            try:
                with urllib.request.urlopen(request, timeout=max(15, int(os.getenv("OPENAI_TIMEOUT_S", "120")))) as response:
                    raw = response.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")
                last_error = RuntimeError(f"OpenAI responses request failed ({exc.code}): {clip_text(error_body, max_chars=800)}")
                continue
            except urllib.error.URLError as exc:
                last_error = RuntimeError(f"OpenAI responses request error: {type(exc).__name__}: {exc}")
                continue
            except Exception as exc:
                last_error = RuntimeError(f"OpenAI responses request failed: {type(exc).__name__}: {exc}")
                continue
            try:
                payload_obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"OpenAI responses returned invalid JSON: {clip_text(raw, max_chars=800)}") from exc
            if not isinstance(payload_obj, dict):
                raise RuntimeError(f"OpenAI responses returned non-object payload: {clip_text(raw, max_chars=800)}")
            return payload_obj
    if last_error is not None:
        raise last_error
    raise RuntimeError("OpenAI responses request failed with unknown error.")


def openai_chat_completions_request(
    *,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    max_tokens: int,
    temperature: float | None,
) -> dict[str, Any]:
    """Optional legacy fallback path for chat-completions transports."""
    url = f"{_openai_base_url()}/chat/completions"
    base_payload: dict[str, Any] = {"model": model, "messages": messages}
    if tools:
        base_payload["tools"] = tools
        base_payload["tool_choice"] = "auto"
    if temperature is not None:
        base_payload["temperature"] = float(temperature)

    token_fields: list[str | None] = [None]
    if int(max_tokens) > 0:
        token_fields = ["max_completion_tokens", "max_tokens"]
    temperature_options: list[float | None] = [None]
    if temperature is not None:
        temperature_options = [float(temperature), None]

    last_error: Exception | None = None
    for token_field in token_fields:
        for maybe_temperature in temperature_options:
            payload = dict(base_payload)
            if token_field is not None:
                payload[token_field] = int(max_tokens)
                other_field = "max_tokens" if token_field == "max_completion_tokens" else "max_completion_tokens"
                payload.pop(other_field, None)
            if maybe_temperature is None:
                payload.pop("temperature", None)
            else:
                payload["temperature"] = maybe_temperature
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            request = urllib.request.Request(url=url, data=body, method="POST")
            request.add_header("Authorization", f"Bearer {api_key}")
            request.add_header("Content-Type", "application/json")
            request.add_header("Accept", "application/json")
            try:
                with urllib.request.urlopen(request, timeout=max(15, int(os.getenv("OPENAI_TIMEOUT_S", "120")))) as response:
                    raw = response.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")
                last_error = RuntimeError(f"OpenAI chat completion failed ({exc.code}): {clip_text(error_body, max_chars=800)}")
                continue
            except urllib.error.URLError as exc:
                last_error = RuntimeError(f"OpenAI chat completion request error: {type(exc).__name__}: {exc}")
                continue
            except Exception as exc:
                last_error = RuntimeError(f"OpenAI chat completion request failed: {type(exc).__name__}: {exc}")
                continue
            try:
                payload_obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"OpenAI chat completion returned invalid JSON: {clip_text(raw, max_chars=800)}") from exc
            if not isinstance(payload_obj, dict):
                raise RuntimeError(f"OpenAI chat completion returned non-object payload: {clip_text(raw, max_chars=800)}")
            return payload_obj
    if last_error is not None:
        raise last_error
    raise RuntimeError("OpenAI chat completion failed with unknown error.")


@dataclass(frozen=True)
class _OpenAIUsageWrapper:
    payload: dict[str, Any]

    def model_dump(self) -> dict[str, Any]:
        return dict(self.payload)


@dataclass(frozen=True)
class _OpenAITextBlock:
    text: str

    def model_dump(self) -> dict[str, Any]:
        return {"type": "text", "text": self.text}


@dataclass(frozen=True)
class _OpenAICompatResponse:
    content: list[_OpenAITextBlock]
    usage: _OpenAIUsageWrapper


class OpenAICompatMessagesAPI:
    """
    Anthropic-like `.messages.create(...)` shim on top of OpenAI APIs.

    This keeps judge/lesson generation call-sites unchanged while allowing
    Responses-first transport underneath.
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
    ) -> _OpenAICompatResponse:
        system_prompt = _extract_system_prompt_text(system)
        if _openai_use_chat_completions():
            payload = openai_chat_completions_request(
                api_key=self._api_key,
                model=model,
                messages=_anthropic_messages_to_openai_messages(messages=messages or [], system_prompt=system_prompt),
                tools=None,
                max_tokens=max(0, int(max_tokens)),
                temperature=temperature,
            )
            choices = payload.get("choices", [])
            if not (isinstance(choices, list) and choices):
                raise RuntimeError("OpenAI chat completion returned no choices.")
            first_choice = choices[0] if isinstance(choices[0], dict) else {}
            message = first_choice.get("message", {})
            if not isinstance(message, dict):
                raise RuntimeError("OpenAI chat completion choice missing message object.")
            raw_text = _openai_message_content_to_text(message.get("content"))
            if not raw_text:
                refusal = str(message.get("refusal", "")).strip()
                raw_text = refusal or ""
            api_variant = "chat_completions"
        else:
            payload = openai_responses_request(
                api_key=self._api_key,
                model=model,
                input_items=anthropic_messages_to_openai_responses_input(messages=messages or []),
                instructions=system_prompt,
                tools=None,
                max_tokens=max(0, int(max_tokens)),
                temperature=temperature,
            )
            raw_text = _openai_responses_output_to_text(payload)
            api_variant = "responses"

        usage_raw = payload.get("usage", {})
        usage = usage_raw if isinstance(usage_raw, dict) else {}
        response_id = str(payload.get("id", "")).strip()
        usage_payload = {
            "backend": "openai",
            "model": model,
            "response_id": response_id,
            "api": api_variant,
            **usage,
        }
        return _OpenAICompatResponse(
            content=[_OpenAITextBlock(text=raw_text)],
            usage=_OpenAIUsageWrapper(payload=usage_payload),
        )


class OpenAICompatClient:
    def __init__(self, *, api_key: str) -> None:
        self.messages = OpenAICompatMessagesAPI(api_key=api_key)


def create_executor_response_via_openai(
    *,
    api_key: str,
    model: str,
    system_prompt: str,
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    temperature: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Run one executor turn via OpenAI transport and normalize it to Anthropic-style blocks.

    This preserves the existing runtime loop contract (`text` + `tool_use` blocks).
    """
    tool_names = [str(tool.get("name", "")).strip() for tool in tools if isinstance(tool, dict)]
    allowed_tool_names = {name for name in tool_names if name}
    assistant_blocks: list[dict[str, Any]] = []

    def _decode_tool_arguments(raw_arguments: Any, *, call_kind: str, tool_name: str) -> tuple[dict[str, Any] | None, str | None]:
        if isinstance(raw_arguments, dict):
            return raw_arguments, None
        raw_arguments_text = str(raw_arguments or "").strip() or "{}"
        try:
            parsed = json.loads(raw_arguments_text)
        except json.JSONDecodeError:
            try:
                parsed = extract_first_json_object(raw_arguments_text)
            except Exception:
                clipped = clip_text(raw_arguments_text, max_chars=500)
                return None, (
                    f"[openai_tool_parse_error] {call_kind} '{tool_name}' arguments were not valid JSON "
                    f"and were skipped: {clipped}"
                )
        if not isinstance(parsed, dict):
            return None, f"[openai_tool_parse_error] {call_kind} '{tool_name}' arguments decoded to non-object and were skipped."
        return parsed, None

    if _openai_use_chat_completions():
        payload = openai_chat_completions_request(
            api_key=api_key,
            model=model,
            messages=_anthropic_messages_to_openai_messages(messages=messages, system_prompt=system_prompt),
            tools=_anthropic_tools_to_openai_tools(tools),
            max_tokens=1800,
            temperature=temperature,
        )
        choices = payload.get("choices", [])
        if not (isinstance(choices, list) and choices):
            raise RuntimeError("OpenAI executor response did not contain choices.")
        first_choice = choices[0] if isinstance(choices[0], dict) else {}
        message = first_choice.get("message", {})
        if not isinstance(message, dict):
            raise RuntimeError("OpenAI executor response missing message object.")
        assistant_text = _openai_message_content_to_text(message.get("content"))
        if assistant_text:
            assistant_blocks.append({"type": "text", "text": assistant_text})
        tool_calls = message.get("tool_calls", [])
        if tool_calls is None:
            tool_calls = []
        if not isinstance(tool_calls, list):
            raise RuntimeError(f"OpenAI executor tool_calls must be list, got {type(tool_calls).__name__}")
        for idx, call in enumerate(tool_calls):
            if not isinstance(call, dict):
                raise RuntimeError(f"OpenAI executor tool call at index {idx} must be object.")
            function = call.get("function", {})
            if not isinstance(function, dict):
                raise RuntimeError(f"OpenAI executor tool call at index {idx} missing function object.")
            name = str(function.get("name", "")).strip()
            if not name:
                raise RuntimeError(f"OpenAI executor tool call at index {idx} missing function name.")
            if name not in allowed_tool_names:
                raise RuntimeError(f"OpenAI requested unknown tool '{name}'. Allowed: {sorted(allowed_tool_names)}")
            tool_input, parse_warning = _decode_tool_arguments(
                function.get("arguments", "{}"),
                call_kind="tool_call",
                tool_name=name,
            )
            if parse_warning:
                assistant_blocks.append({"type": "text", "text": parse_warning})
                continue
            if tool_input is None:
                continue
            tool_call_id = str(call.get("id", "")).strip() or f"toolu_openai_{uuid.uuid4().hex[:12]}_{idx}"
            assistant_blocks.append({"type": "tool_use", "id": tool_call_id, "name": name, "input": tool_input})
        api_variant = "chat_completions"
    else:
        payload = openai_responses_request(
            api_key=api_key,
            model=model,
            input_items=anthropic_messages_to_openai_responses_input(messages=messages),
            instructions=system_prompt,
            tools=_anthropic_tools_to_openai_responses_tools(tools),
            max_tokens=1800,
            temperature=temperature,
        )
        assistant_text = _openai_responses_output_to_text(payload)
        if assistant_text:
            assistant_blocks.append({"type": "text", "text": assistant_text})
        output_items = payload.get("output", [])
        if output_items is None:
            output_items = []
        if not isinstance(output_items, list):
            raise RuntimeError(f"OpenAI executor output must be list, got {type(output_items).__name__}")
        call_index = 0
        for idx, item in enumerate(output_items):
            if not isinstance(item, dict):
                continue
            if str(item.get("type", "")).strip().lower() != "function_call":
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                raise RuntimeError(f"OpenAI function_call at output index {idx} missing name.")
            if name not in allowed_tool_names:
                raise RuntimeError(f"OpenAI requested unknown tool '{name}'. Allowed: {sorted(allowed_tool_names)}")
            tool_input, parse_warning = _decode_tool_arguments(
                item.get("arguments", "{}"),
                call_kind="function_call",
                tool_name=name,
            )
            if parse_warning:
                assistant_blocks.append({"type": "text", "text": parse_warning})
                continue
            if tool_input is None:
                continue
            tool_call_id = str(item.get("call_id", "")).strip() or f"toolu_openai_{uuid.uuid4().hex[:12]}_{call_index}"
            call_index += 1
            assistant_blocks.append({"type": "tool_use", "id": tool_call_id, "name": name, "input": tool_input})
        api_variant = "responses"

    usage_raw = payload.get("usage", {})
    usage = usage_raw if isinstance(usage_raw, dict) else {}
    usage_payload = {
        "backend": "openai",
        "model": model,
        "response_id": str(payload.get("id", "")).strip(),
        "api": api_variant,
        **usage,
    }
    return assistant_blocks, usage_payload

