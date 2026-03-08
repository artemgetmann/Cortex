from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Callable

from claude_print_runtime import (
    assistant_blocks_from_claude_print_payload,
    build_claude_print_env,
    clip_text,
    extract_first_json_object,
    normalize_claude_print_effort,
    render_message_history_for_claude_print,
    resolve_claude_print_model,
)
from tracks.cli_sqlite.openai_agents_sdk_transport import (
    OpenAIAgentsSDKExecutionState,
    create_executor_response_via_openai_agents_sdk as _create_executor_response_via_openai_agents_sdk,
)
from tracks.cli_sqlite.openai_transport import (
    create_executor_response_via_openai as _create_executor_response_via_openai,
)


def _clip_text(text: str, *, max_chars: int = 4000) -> str:
    return clip_text(text, max_chars=max_chars)


def _render_message_history_for_claude_print(messages: list[dict[str, Any]]) -> str:
    return render_message_history_for_claude_print(messages, max_messages=20)


def _extract_first_json_object(raw: str) -> dict[str, Any]:
    return extract_first_json_object(raw, max_error_chars=500)


def _assistant_blocks_from_claude_print_payload(
    *,
    payload: dict[str, Any],
    allowed_tool_names: set[str],
) -> list[dict[str, Any]]:
    return assistant_blocks_from_claude_print_payload(
        payload=payload,
        allowed_tool_names=allowed_tool_names,
    )


def create_executor_response_via_claude_print(
    *,
    model: str,
    system_prompt: str,
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    prompt_logger: Callable[[str], None] | None = None,
    fallback_model: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run one executor turn via `claude -p` and return synthetic assistant blocks."""
    tool_names = [str(tool.get("name", "")).strip() for tool in tools if isinstance(tool, dict)]
    allowed_tool_names = {name for name in tool_names if name}
    tools_for_prompt = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name", "")).strip()
        if not name:
            continue
        tools_for_prompt.append(
            {
                "name": name,
                "description": str(tool.get("description", "")).strip(),
                "input_schema": tool.get("input_schema", {}),
            }
        )
    history_text = _render_message_history_for_claude_print(messages)
    prompt = (
        "You are the planner for a tool-using loop.\n"
        "Return exactly one JSON object with this shape:\n"
        "{\n"
        '  "assistant_text": "short reasoning",\n'
        '  "tool_calls": [{"name":"tool_name","input":{...}}]\n'
        "}\n"
        "Rules:\n"
        "- Use ONLY tools listed below.\n"
        "- tool_calls may contain multiple calls, or be empty if task is done.\n"
        "- input must match each tool input_schema.\n"
        "- Do not wrap JSON in markdown.\n\n"
        f"SYSTEM_PROMPT:\n{system_prompt}\n\n"
        f"TOOLS:\n{json.dumps(tools_for_prompt, ensure_ascii=True, indent=2, sort_keys=True)}\n\n"
        f"MESSAGE_HISTORY:\n{history_text}\n"
    )
    if prompt_logger is not None:
        prompt_logger(prompt)
    timeout_s = max(10, int(os.getenv("CORTEX_CLAUDE_PRINT_TIMEOUT_S", "90")))
    requested_model, effective_model = resolve_claude_print_model(
        model,
        fallback_model=fallback_model,
    )
    effort = normalize_claude_print_effort(None, default="high")
    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "text",
        "--tools",
        "",
        "--effort",
        effort,
    ]
    cmd.extend(["--model", effective_model])
    cmd_env = build_claude_print_env()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            env=cmd_env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"claude -p executor turn timed out after {timeout_s}s. "
            "Try lowering prompt size, using a faster model, or increasing CORTEX_CLAUDE_PRINT_TIMEOUT_S."
        ) from exc
    stdout = str(proc.stdout or "")
    stderr = str(proc.stderr or "")
    if proc.returncode != 0:
        raise RuntimeError(
            "claude -p executor turn failed "
            f"(code={proc.returncode}): {_clip_text(stderr or stdout, max_chars=800)}"
        )
    payload = _extract_first_json_object(stdout)
    blocks = _assistant_blocks_from_claude_print_payload(
        payload=payload,
        allowed_tool_names=allowed_tool_names,
    )
    usage = {
        "backend": "claude_print",
        "model": effective_model,
        "requested_model": requested_model,
        "effort": effort,
        "stdout_chars": len(stdout),
        "stderr_chars": len(stderr),
    }
    return blocks, usage


def request_executor_turn(
    *,
    llm_backend: str,
    client: Any,
    openai_api_key: str,
    model: str,
    system_prompt: str,
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    runtime_temperature: float | None,
    tool_choice_override: str | None = None,
    prompt_logger: Callable[[str], None] | None = None,
    claude_print_fallback_model: str,
    sdk_execution_state: OpenAIAgentsSDKExecutionState | None = None,
    sdk_execution_context: bool = True,
    openai_request_fn: Callable[..., tuple[list[dict[str, Any]], dict[str, Any]]] = _create_executor_response_via_openai,
    openai_agents_request_fn: Callable[..., tuple[list[dict[str, Any]], dict[str, Any]]] = _create_executor_response_via_openai_agents_sdk,
    claude_print_request_fn: Callable[..., tuple[list[dict[str, Any]], dict[str, Any]]] = create_executor_response_via_claude_print,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Route one executor turn to the configured transport.

    This keeps transport branching in one place so the runtime loop can stay
    focused on tool execution and learning logic.
    """
    if llm_backend == "anthropic":
        if client is None:
            raise RuntimeError("Anthropic client unavailable while llm_backend=anthropic.")
        request: dict[str, Any] = {
            "model": model,
            "max_tokens": 1800,
            "system": system_prompt,
            "tools": tools,
            "messages": messages,
        }
        if runtime_temperature is not None:
            request["temperature"] = float(runtime_temperature)
        response = client.messages.create(**request)
        try:
            usage = response.usage.model_dump()  # type: ignore[attr-defined]
        except Exception:
            usage_obj = getattr(response, "usage", None)
            usage = usage_obj.model_dump() if usage_obj is not None and hasattr(usage_obj, "model_dump") else {}
        assistant_blocks = [block.model_dump() for block in response.content]  # type: ignore[attr-defined]
        return assistant_blocks, usage

    if llm_backend == "openai":
        return openai_request_fn(
            api_key=openai_api_key,
            model=model,
            system_prompt=system_prompt,
            tools=tools,
            messages=messages,
            temperature=runtime_temperature,
            tool_choice_override=tool_choice_override,
        )

    if llm_backend == "openai_agents_sdk":
        return openai_agents_request_fn(
            api_key=openai_api_key,
            model=model,
            system_prompt=system_prompt,
            tools=tools,
            messages=messages,
            temperature=runtime_temperature,
            execution_state=sdk_execution_state,
            execution_context=bool(sdk_execution_context),
        )

    return claude_print_request_fn(
        model=model,
        system_prompt=system_prompt,
        tools=tools,
        messages=messages,
        prompt_logger=prompt_logger,
        fallback_model=claude_print_fallback_model,
    )
