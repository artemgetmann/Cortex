from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic

from config import CortexConfig
from computer_use import ComputerTool, ToolResult
from memory import ensure_session, read_text, write_event, write_metrics


BASE_SYSTEM_PROMPT = """You are controlling FL Studio Desktop on macOS via screenshots and mouse/keyboard.

Rules:
- Keyboard first. Prefer shortcuts over clicking whenever possible.
- Prefer Hint Bar verification: before clicking any UI element, move the mouse to the target and use a screenshot to read the Hint Bar text.
  If the Hint Bar is not visible/readable, proceed using zoom + visual confirmation instead (do not get stuck).
- After every action, verify the UI changed as expected. If not, undo (Ctrl+Z) and try an alternative.
- Keep the run safe: do not interact with anything outside FL Studio.
- Never use OS-level shortcuts: do not press Command+Q, Command+Tab, Command+W, Command+M, or anything intended to quit/switch apps.
"""


def build_system_prompt(*, tool_api_type: str) -> str:
    # zoom exists only on computer_20251124
    zoom_line = ""
    if tool_api_type == "computer_20251124":
        zoom_line = "- Use the zoom action when UI elements are small/dense.\n"
    return BASE_SYSTEM_PROMPT + "\n" + zoom_line


PROMPT_CACHING_BETA_FLAG = "prompt-caching-2024-07-31"


def _inject_prompt_caching(messages: list[dict[str, Any]], *, breakpoints: int = 3) -> None:
    """
    Put cache breakpoints on the most recent user turns so repeated loops are cheap.
    Mirrors Anthropic quickstart behavior.
    """
    remaining = breakpoints
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if not isinstance(content, list) or not content:
            continue
        if remaining > 0:
            remaining -= 1
            last = content[-1]
            if isinstance(last, dict):
                last["cache_control"] = {"type": "ephemeral"}
        else:
            last = content[-1]
            if isinstance(last, dict) and "cache_control" in last:
                del last["cache_control"]
            break


def _tool_result_block(tool_use_id: str, result: ToolResult) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    if result.output:
        content.append({"type": "text", "text": result.output})
    if result.error:
        content.append({"type": "text", "text": result.error})
    if result.base64_image_png:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": result.base64_image_png,
                },
            }
        )
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "is_error": result.is_error(),
        "content": content or "",
    }


def _save_png_b64(session_dir: Path, *, name: str, b64: str) -> Path:
    out = session_dir / name
    out.write_bytes(base64.b64decode(b64))
    return out


@dataclass
class RunResult:
    messages: list[dict[str, Any]]
    metrics: dict[str, Any]


def run_agent(
    *,
    cfg: CortexConfig,
    task: str,
    session_id: int,
    max_steps: int = 80,
    model: str,
    allowed_actions: set[str] | None = None,
) -> RunResult:
    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key, max_retries=3)

    # Tool version + beta flag must match the model's supported computer tool.
    if model == cfg.model_heavy:
        computer_api_type = cfg.computer_tool_type_heavy
        computer_beta = cfg.computer_use_beta_heavy
    else:
        computer_api_type = cfg.computer_tool_type_decider
        computer_beta = cfg.computer_use_beta_decider

    computer = ComputerTool(
        api_type=computer_api_type,
        display_width_px=cfg.display_width_px,
        display_height_px=cfg.display_height_px,
        enable_zoom=(computer_api_type == "computer_20251124"),
    )

    paths = ensure_session(session_id)

    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": [{"type": "text", "text": task}],
        }
    ]

    # System is split so we can put the cache breakpoint after stable "skills" text.
    # This mirrors Anthropic prompt caching guidance: keep the prefix stable.
    base_system_block: dict[str, Any] = {"type": "text", "text": build_system_prompt(tool_api_type=computer_api_type)}

    skills_text_parts: list[str] = []
    skills_index = Path("skills/fl-studio/index.md")
    if skills_index.exists():
        skills_text_parts.append("## Skills Index\n" + read_text(skills_index))
    # Default: include the first hand-written skill doc if it exists.
    drum_skill = Path("skills/fl-studio/drum-pattern.md")
    if drum_skill.exists():
        skills_text_parts.append("## Skill: drum-pattern\n" + read_text(drum_skill))
    skills_system_block: dict[str, Any] = {"type": "text", "text": "\n\n".join(skills_text_parts).strip() or "No skills loaded."}
    system_blocks = [base_system_block, skills_system_block]

    betas = [computer_beta]
    if cfg.enable_prompt_caching:
        betas.append(PROMPT_CACHING_BETA_FLAG)
        # Cache after skills block so it can be reused across loop turns.
        skills_system_block["cache_control"] = {"type": "ephemeral"}
    # Reduce screenshot/tool payload overhead when supported.
    # If unsupported by the model, the API will 400; we'll disable if that happens.
    betas.append(cfg.token_efficient_tools_beta)

    metrics: dict[str, Any] = {
        "session_id": session_id,
        "model": model,
        "time_start": time.time(),
        "steps": 0,
        "tool_actions": 0,
        "tool_errors": 0,
        "usage": [],
    }

    for step in range(1, max_steps + 1):
        metrics["steps"] = step
        if cfg.enable_prompt_caching:
            _inject_prompt_caching(messages)

        try:
            resp = client.beta.messages.create(
                model=model,
                max_tokens=2048,
                system=system_blocks,
                tools=[computer.to_tool_param()],
                messages=messages,
                betas=betas,
            )
        except anthropic.BadRequestError as e:
            # If the token-efficient-tools beta isn't supported, retry once without it.
            msg = str(getattr(e, "message", "")) + " " + str(getattr(e, "body", ""))
            if cfg.token_efficient_tools_beta in msg and cfg.token_efficient_tools_beta in betas:
                betas = [b for b in betas if b != cfg.token_efficient_tools_beta]
                resp = client.beta.messages.create(
                    model=model,
                    max_tokens=2048,
                    system=system_blocks,
                    tools=[computer.to_tool_param()],
                    messages=messages,
                    betas=betas,
                )
            else:
                raise

        # Usage accounting (incl. prompt caching fields when enabled)
        try:
            usage = resp.usage.model_dump()  # type: ignore[attr-defined]
        except Exception:
            usage = getattr(resp, "usage", None)
            usage = usage.model_dump() if usage is not None and hasattr(usage, "model_dump") else {}
        metrics["usage"].append(usage)

        assistant_blocks = [b.model_dump() for b in resp.content]  # type: ignore[attr-defined]
        messages.append({"role": "assistant", "content": assistant_blocks})

        tool_results: list[dict[str, Any]] = []

        for block in assistant_blocks:
            if not (isinstance(block, dict) and block.get("type") == "tool_use"):
                continue
            tool_use_id = block.get("id", "")
            tool_name = block.get("name", "")
            tool_input = block.get("input", {})

            if tool_name != computer.name:
                result = ToolResult(error=f"Unknown tool requested: {tool_name!r}")
            else:
                metrics["tool_actions"] += 1
                try:
                    tool_in = tool_input if isinstance(tool_input, dict) else {}
                    action = tool_in.get("action")
                    if allowed_actions is not None:
                        if not isinstance(action, str) or action not in allowed_actions:
                            result = ToolResult(error=f"Action not allowed in this run: {action!r}")
                        else:
                            result = computer.run(tool_in)
                    else:
                        result = computer.run(tool_in)
                except Exception as e:
                    # Don't crash the loop on unexpected local tool errors; surface it to the model.
                    result = ToolResult(error=f"Local tool exception: {type(e).__name__}: {e}")
                if result.is_error():
                    metrics["tool_errors"] += 1

            if result.base64_image_png:
                img_path = _save_png_b64(paths.session_dir, name=f"step-{step:03d}.png", b64=result.base64_image_png)
            else:
                img_path = None

            write_event(
                paths.jsonl_path,
                {
                    "step": step,
                    "tool": tool_name,
                    "tool_input": tool_input,
                    "ok": not result.is_error(),
                    "error": result.error,
                    "output": result.output,
                    "screenshot": str(img_path) if img_path else None,
                    "usage": usage,
                },
            )

            tool_results.append(_tool_result_block(tool_use_id, result))

        if not tool_results:
            # No tool calls => model claims it's done / can't proceed.
            break

        messages.append({"role": "user", "content": tool_results})

    metrics["time_end"] = time.time()
    metrics["elapsed_s"] = metrics["time_end"] - metrics["time_start"]
    write_metrics(paths.metrics_path, metrics)

    return RunResult(messages=messages, metrics=metrics)
