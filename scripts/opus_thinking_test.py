#!/usr/bin/env python3
"""
Standalone test: run Cortex agent with Opus 4.6 extended thinking enabled.
Copies the core agent loop but adds thinking={type: enabled} to the API call.
Does NOT modify agent.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import base64
import json
import time
from typing import Any

import anthropic

from config import load_config, CortexConfig
from computer_use import ComputerTool, ToolResult
from memory import ensure_session, read_text, write_event, write_metrics


BASE_SYSTEM_PROMPT = """You are controlling FL Studio Desktop on macOS via screenshots and mouse/keyboard.

Rules:
- Keyboard first. Prefer shortcuts over clicking whenever possible.
- Hint Bar verification: hover the target, take a screenshot, read the Hint Bar text at the top-left of the FL Studio window.
  Once the Hint Bar confirms the expected element, immediately act (click, type, etc.). Do not re-verify.
  If 2 hover attempts fail to confirm, skip verification and use visual recognition. Never loop on hover-zoom-read.
- After every action, verify the UI changed as expected. If not, undo (Cmd+Z) and try an alternative.
- Keep the run safe: do not interact with anything outside FL Studio.
- Never use OS-level shortcuts: do not press Command+Q, Command+Tab, Command+W, Command+M, or anything intended to quit/switch apps.
"""


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


def run_thinking_agent(
    *,
    cfg: CortexConfig,
    task: str,
    session_id: int,
    max_steps: int = 24,
    thinking_budget: int = 8000,
) -> dict[str, Any]:
    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key, max_retries=3)

    model = cfg.model_heavy  # claude-opus-4-6
    computer_api_type = cfg.computer_tool_type_heavy
    computer_beta = cfg.computer_use_beta_heavy

    computer = ComputerTool(
        api_type=computer_api_type,
        display_width_px=cfg.display_width_px,
        display_height_px=cfg.display_height_px,
        enable_zoom=(computer_api_type == "computer_20251124"),
    )

    paths = ensure_session(session_id)

    # Load skills
    skills_text_parts: list[str] = []
    skills_index = Path("skills/fl-studio/index.md")
    if skills_index.exists():
        skills_text_parts.append("## Skills Index\n" + read_text(skills_index))
    drum_skill = Path("skills/fl-studio/drum-pattern.md")
    if drum_skill.exists():
        skills_text_parts.append("## Skill: drum-pattern\n" + read_text(drum_skill))
    skills_text = "\n\n".join(skills_text_parts).strip() or "No skills loaded."

    # Zoom line for opus tool
    zoom_line = ""
    if computer_api_type == "computer_20251124":
        zoom_line = "- Use the zoom action when UI elements are small/dense.\n"
    system_text = BASE_SYSTEM_PROMPT + "\n" + zoom_line

    system_blocks = [
        {"type": "text", "text": system_text},
        {"type": "text", "text": skills_text, "cache_control": {"type": "ephemeral"}},
    ]

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": [{"type": "text", "text": task}]},
    ]

    betas = [computer_beta]
    if cfg.enable_prompt_caching:
        betas.append("prompt-caching-2024-07-31")
    betas.append(cfg.token_efficient_tools_beta)

    metrics: dict[str, Any] = {
        "session_id": session_id,
        "model": model,
        "thinking_budget": thinking_budget,
        "time_start": time.time(),
        "steps": 0,
        "tool_actions": 0,
        "tool_errors": 0,
    }

    for step in range(1, max_steps + 1):
        metrics["steps"] = step

        # Inject cache breakpoints on recent user turns
        remaining = 3
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

        try:
            resp = client.beta.messages.create(
                model=model,
                max_tokens=16000,
                thinking={
                    "type": "enabled",
                    "budget_tokens": thinking_budget,
                },
                system=system_blocks,
                tools=[computer.to_tool_param()],
                messages=messages,
                betas=betas,
            )
        except anthropic.BadRequestError as e:
            msg_str = str(getattr(e, "message", "")) + " " + str(getattr(e, "body", ""))
            if cfg.token_efficient_tools_beta in msg_str:
                betas = [b for b in betas if b != cfg.token_efficient_tools_beta]
                resp = client.beta.messages.create(
                    model=model,
                    max_tokens=16000,
                    thinking={
                        "type": "enabled",
                        "budget_tokens": thinking_budget,
                    },
                    system=system_blocks,
                    tools=[computer.to_tool_param()],
                    messages=messages,
                    betas=betas,
                )
            else:
                raise

        try:
            usage = resp.usage.model_dump()
        except Exception:
            usage = {}

        assistant_blocks = [b.model_dump() for b in resp.content]
        messages.append({"role": "assistant", "content": assistant_blocks})

        # Print any thinking blocks
        for block in assistant_blocks:
            if isinstance(block, dict) and block.get("type") == "thinking":
                thinking_text = block.get("thinking", "")
                if thinking_text:
                    preview = thinking_text[:200].replace("\n", " ")
                    print(f"  [thinking] {preview}{'...' if len(thinking_text) > 200 else ''}", flush=True)

        tool_results: list[dict[str, Any]] = []

        for block in assistant_blocks:
            if not (isinstance(block, dict) and block.get("type") == "tool_use"):
                continue
            tool_use_id = block.get("id", "")
            tool_name = block.get("name", "")
            tool_input = block.get("input", {})

            if tool_name != computer.name:
                result = ToolResult(error=f"Unknown tool: {tool_name!r}")
            else:
                metrics["tool_actions"] += 1
                try:
                    result = computer.run(tool_input if isinstance(tool_input, dict) else {})
                except Exception as e:
                    result = ToolResult(error=f"Exception: {type(e).__name__}: {e}")
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

            action = tool_input.get("action") if isinstance(tool_input, dict) else None
            print(
                f"[step {step:03d}] tool={tool_name} action={action!r} ok={not result.is_error()} error={result.error!r}",
                flush=True,
            )

            tool_results.append(_tool_result_block(tool_use_id, result))

        if not tool_results:
            print(f"[step {step:03d}] no tool call; model stopped.", flush=True)
            break

        messages.append({"role": "user", "content": tool_results})

    metrics["time_end"] = time.time()
    metrics["elapsed_s"] = metrics["time_end"] - metrics["time_start"]
    write_metrics(paths.metrics_path, metrics)
    return metrics


def main() -> int:
    ap = argparse.ArgumentParser(description="Opus 4.6 thinking test")
    ap.add_argument("--task", required=True)
    ap.add_argument("--session", type=int, default=9901)
    ap.add_argument("--max-steps", type=int, default=24)
    ap.add_argument("--thinking-budget", type=int, default=8000)
    args = ap.parse_args()

    cfg = load_config()
    metrics = run_thinking_agent(
        cfg=cfg,
        task=args.task,
        session_id=args.session,
        max_steps=args.max_steps,
        thinking_budget=args.thinking_budget,
    )
    print("\nmetrics:", json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
