from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any


# Shared Claude Print runtime helpers used by both FL and CLI tracks.
# Keeping this module transport-focused prevents drift between orchestrators.

# Shared backend constants used by both FL and CLI runtime tracks.
LLM_BACKENDS = ("anthropic", "claude_print")
DEFAULT_LLM_BACKEND = "claude_print"
VALID_CLAUDE_PRINT_EFFORTS = {"low", "medium", "high"}


def clip_text(text: str, *, max_chars: int = 4000) -> str:
    """Bound very large strings to keep logs/errors readable."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def normalize_llm_backend(value: str) -> str:
    """Normalize and validate backend names once in a shared place."""
    normalized = str(value or "").strip().lower()
    if normalized not in LLM_BACKENDS:
        raise ValueError(f"Unsupported llm_backend: {value!r}. Expected one of {LLM_BACKENDS}.")
    return normalized


def normalize_claude_print_effort(requested_effort: str | None, *, default: str = "high") -> str:
    """
    Resolve effort in priority order:
    explicit arg -> env -> default.
    """
    effort = str(requested_effort or "").strip().lower()
    if not effort:
        effort = os.getenv("CORTEX_CLAUDE_PRINT_EFFORT", default).strip().lower() or default
    if effort not in VALID_CLAUDE_PRINT_EFFORTS:
        effort = default
    return effort


def resolve_claude_print_model(requested_model: str | None, *, fallback_model: str) -> tuple[str, str]:
    """
    Return (requested_model, effective_model).
    Effective model may be forced by env for operators running global overrides.
    """
    requested = str(requested_model or "").strip() or fallback_model
    env_model_override = os.getenv("CORTEX_CLAUDE_PRINT_MODEL", "").strip()
    effective = env_model_override or requested
    return requested, effective


def build_claude_print_env() -> dict[str, str]:
    """Build subprocess env with subscription auth as the safe default."""
    cmd_env = os.environ.copy()
    allow_api_key = os.getenv("CORTEX_CLAUDE_PRINT_USE_API_KEY", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    # Default behavior is subscription-backed CLI auth.
    if not allow_api_key:
        cmd_env.pop("ANTHROPIC_API_KEY", None)
    return cmd_env


def render_message_history_for_claude_print(
    messages: list[dict[str, Any]],
    *,
    max_messages: int = 12,
    include_tool_result_image_hint: bool = False,
) -> str:
    """
    Flatten Anthropic-style message blocks into deterministic text history.

    This keeps `claude -p` prompts compact and stable while preserving tool context.
    """
    lines: list[str] = []
    for msg in messages[-max_messages:]:
        role = str(msg.get("role", "user")).strip() or "user"
        lines.append(f"ROLE: {role}")
        blocks = msg.get("content")
        if not isinstance(blocks, list):
            lines.append(str(blocks))
            lines.append("")
            continue

        for block in blocks:
            if not isinstance(block, dict):
                lines.append(str(block))
                continue
            block_type = str(block.get("type", "")).strip().lower()
            if block_type == "text":
                text = str(block.get("text", "")).strip()
                if text:
                    lines.append(f"TEXT: {text}")
            elif block_type == "tool_use":
                tool_name = str(block.get("name", "")).strip()
                tool_input = json.dumps(block.get("input", {}), ensure_ascii=True, sort_keys=True)
                lines.append(f"TOOL_USE {tool_name}: {tool_input}")
            elif block_type == "tool_result":
                tool_use_id = str(block.get("tool_use_id", "")).strip()
                is_error = bool(block.get("is_error", False))
                content = block.get("content")
                text_parts: list[str] = []
                has_image = False
                if isinstance(content, list):
                    for part in content:
                        if not isinstance(part, dict):
                            continue
                        part_type = str(part.get("type", "")).strip().lower()
                        if part_type == "text":
                            text_parts.append(str(part.get("text", "")))
                        elif part_type == "image":
                            has_image = True
                elif isinstance(content, str):
                    text_parts.append(content)
                merged = " ".join(part for part in text_parts if part).strip()
                if include_tool_result_image_hint and has_image:
                    merged = f"{merged} [screenshot-attached]".strip()
                lines.append(f"TOOL_RESULT {tool_use_id} error={is_error}: {merged}")
            else:
                lines.append(json.dumps(block, ensure_ascii=True, sort_keys=True))
        lines.append("")
    return "\n".join(lines).strip()


def extract_first_json_object(raw: str, *, max_error_chars: int = 600) -> dict[str, Any]:
    """
    Parse first JSON object from model text output.

    Handles fenced code blocks and noisy pre/post text, then falls back to
    scanning from each `{` boundary.
    """
    text = str(raw or "").strip()
    if not text:
        raise RuntimeError("claude -p returned empty output.")

    # Fast-path for fenced JSON responses.
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    # Exact parse first, then resilient scan.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj

    raise RuntimeError(f"claude -p output is not valid JSON object: {clip_text(text, max_chars=max_error_chars)}")


def assistant_blocks_from_claude_print_payload(
    *,
    payload: dict[str, Any],
    allowed_tool_names: set[str],
    id_prefix: str = "toolu_cli",
) -> list[dict[str, Any]]:
    """
    Convert strict JSON payload into Anthropic-like assistant blocks.

    Tool validation here is intentionally strict because this is the boundary
    between untrusted model output and local tool execution.
    """
    assistant_text = str(payload.get("assistant_text", "")).strip()
    blocks: list[dict[str, Any]] = []
    if assistant_text:
        blocks.append({"type": "text", "text": assistant_text})

    tool_calls = payload.get("tool_calls", [])
    if not isinstance(tool_calls, list):
        raise RuntimeError(f"claude -p payload 'tool_calls' must be list, got: {type(tool_calls).__name__}")

    for idx, call in enumerate(tool_calls):
        if not isinstance(call, dict):
            raise RuntimeError(f"claude -p tool call at index {idx} must be object, got: {type(call).__name__}")
        name = str(call.get("name", "")).strip()
        tool_input = call.get("input", {})
        if not name:
            raise RuntimeError(f"claude -p tool call at index {idx} missing 'name'.")
        if name not in allowed_tool_names:
            raise RuntimeError(f"claude -p requested unknown tool '{name}'. Allowed: {sorted(allowed_tool_names)}")
        if not isinstance(tool_input, dict):
            raise RuntimeError(
                f"claude -p tool call '{name}' input must be object, got: {type(tool_input).__name__}"
            )
        blocks.append(
            {
                "type": "tool_use",
                "id": f"{id_prefix}_{uuid.uuid4().hex[:12]}_{idx}",
                "name": name,
                "input": tool_input,
            }
        )
    return blocks


def extract_stream_json_result(stdout: str) -> tuple[str, dict[str, Any]]:
    """
    Extract final `result` event and optional usage payload from stream-json output.
    """
    result_text = ""
    usage_payload: dict[str, Any] = {}

    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            evt = json.loads(stripped)
        except Exception:
            continue
        if not isinstance(evt, dict):
            continue
        if str(evt.get("type")) == "result":
            result_text = str(evt.get("result", "") or "")
            usage = evt.get("usage")
            if isinstance(usage, dict):
                usage_payload = usage

    return result_text, usage_payload
