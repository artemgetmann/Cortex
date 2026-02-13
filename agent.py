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
from memory import ensure_session, write_event, write_metrics
from self_improve import apply_skill_updates, parse_reflection_response, skill_digest
from skill_routing import (
    SkillManifestEntry,
    build_skill_manifest,
    manifest_summaries_text,
    resolve_skill_content,
    route_manifest_entries,
)


BASE_SYSTEM_PROMPT = """You are controlling FL Studio Desktop on macOS via screenshots and mouse/keyboard.

Rules:
- Keyboard first. Prefer shortcuts over clicking whenever possible.
- Keep verification lightweight. Confirm ambiguous targets once, then act.
- Do not loop on inspection actions. If two inspections fail to increase confidence, switch to a decisive action.
- After every action, verify the UI changed as expected. If not, try one alternative and move on.
- Use app-specific skills for UI conventions and domain workflows.
- Keep the run safe: do not interact with anything outside FL Studio.
- Never use OS-level shortcuts: do not press Command+Q, Command+Tab, Command+W, Command+M, or anything intended to quit/switch apps.
"""


def build_system_prompt(*, tool_api_type: str) -> str:
    # zoom exists only on computer_20251124
    zoom_line = ""
    no_zoom_line = ""
    if tool_api_type == "computer_20251124":
        zoom_line = "- Use the zoom action when UI elements are small/dense.\n"
    else:
        no_zoom_line = (
            "- Zoom action is unavailable in this run. Do not attempt keyboard zoom aliases "
            "(minus, plus, kp_subtract, kp_add), pinch-style behavior, or exploratory scroll "
            "as a zoom substitute.\n"
            "- If an unsupported key name fails once, do not retry key-name variants. "
            "Switch to another supported action.\n"
        )
    return BASE_SYSTEM_PROMPT + "\n" + zoom_line + no_zoom_line


PROMPT_CACHING_BETA_FLAG = "prompt-caching-2024-07-31"
READ_SKILL_TOOL_NAME = "read_skill"
NON_PRODUCTIVE_ACTIONS = {"zoom", "mouse_move"}
RESET_NON_PRODUCTIVE_ACTIONS = {"left_click", "key"}


def _read_skill_tool_param() -> dict[str, Any]:
    return {
        "name": READ_SKILL_TOOL_NAME,
        "description": (
            "Read full contents of a skill document by stable skill_ref. "
            "Use this only when title/description metadata is not enough."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_ref": {
                    "type": "string",
                    "description": "Stable skill reference from skill metadata list.",
                }
            },
            "required": ["skill_ref"],
            "additionalProperties": False,
        },
    }


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
    load_skills: bool = True,
    posttask_learn: bool = True,
    verbose: bool = False,
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
    skill_manifest_entries: list[SkillManifestEntry] = []
    routed_skill_entries: list[SkillManifestEntry] = []

    if load_skills:
        skill_manifest_entries = build_skill_manifest()
        routed_skill_entries = route_manifest_entries(task=task, entries=skill_manifest_entries, top_k=3)
        skills_text = manifest_summaries_text(routed_skill_entries)
    else:
        skills_text = "No skills loaded."
    skills_system_block: dict[str, Any] = {"type": "text", "text": skills_text}
    skill_usage_block: dict[str, Any] = {
        "type": "text",
        "text": (
            "Skills policy:\n"
            "- You only have skill titles and descriptions at start.\n"
            "- If a listed skill may help, call read_skill with that exact skill_ref to fetch full steps.\n"
            "- Do not assume full skill contents without calling read_skill.\n"
            "- Keep read_skill calls targeted; avoid reading every skill."
        ),
    }
    system_blocks = [base_system_block, skills_system_block, skill_usage_block]

    tools: list[dict[str, Any]] = [computer.to_tool_param()]
    if load_skills:
        tools.append(_read_skill_tool_param())

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
        "load_skills": load_skills,
        "tool_actions": 0,
        "skill_reads": 0,
        "tool_errors": 0,
        "loop_guard_blocks": 0,
        "posttask_learn": posttask_learn,
        "posttask_patch_attempted": False,
        "posttask_patch_applied": 0,
        "usage": [],
    }
    # Hard guardrail for Opus path: stop inspection loops and force decisive actions.
    non_productive_streak = 0
    loop_guard_enabled = computer_api_type == "computer_20251124"
    read_skill_refs: set[str] = set()

    for step in range(1, max_steps + 1):
        metrics["steps"] = step
        if cfg.enable_prompt_caching:
            _inject_prompt_caching(messages)

        try:
            resp = client.beta.messages.create(
                model=model,
                max_tokens=2048,
                system=system_blocks,
                tools=tools,
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
                    tools=tools,
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

            if tool_name == computer.name:
                metrics["tool_actions"] += 1
                try:
                    tool_in = tool_input if isinstance(tool_input, dict) else {}
                    action = tool_in.get("action")
                    if loop_guard_enabled and action in NON_PRODUCTIVE_ACTIONS and non_productive_streak >= 2:
                        result = ToolResult(
                            error=(
                                "Loop guard: too many consecutive zoom/mouse_move actions without progress. "
                                "Next action must be decisive: left_click or key."
                            )
                        )
                        metrics["loop_guard_blocks"] += 1
                    elif allowed_actions is not None:
                        if not isinstance(action, str) or action not in allowed_actions:
                            result = ToolResult(error=f"Action not allowed in this run: {action!r}")
                        else:
                            result = computer.run(tool_in)
                    else:
                        result = computer.run(tool_in)

                    if action in NON_PRODUCTIVE_ACTIONS and not result.is_error():
                        non_productive_streak += 1
                    elif action in RESET_NON_PRODUCTIVE_ACTIONS and not result.is_error():
                        non_productive_streak = 0

                except Exception as e:
                    # Don't crash the loop on unexpected local tool errors; surface it to the model.
                    result = ToolResult(error=f"Local tool exception: {type(e).__name__}: {e}")
                if result.is_error():
                    metrics["tool_errors"] += 1
            elif tool_name == READ_SKILL_TOOL_NAME:
                metrics["skill_reads"] += 1
                tool_in = tool_input if isinstance(tool_input, dict) else {}
                skill_ref = tool_in.get("skill_ref")
                if not isinstance(skill_ref, str):
                    result = ToolResult(error=f"read_skill requires string skill_ref, got: {skill_ref!r}")
                    metrics["tool_errors"] += 1
                else:
                    content, err = resolve_skill_content(skill_manifest_entries, skill_ref)
                    if err:
                        result = ToolResult(error=err)
                        metrics["tool_errors"] += 1
                    else:
                        read_skill_refs.add(skill_ref)
                        result = ToolResult(output=f"skill_ref: {skill_ref}\n\n{content}")
            else:
                result = ToolResult(error=f"Unknown tool requested: {tool_name!r}")

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

            if verbose:
                action = tool_input.get("action") if isinstance(tool_input, dict) else None
                print(
                    f"[step {step:03d}] tool={tool_name} action={action!r} ok={not result.is_error()} error={result.error!r}",
                    flush=True,
                )

            tool_results.append(_tool_result_block(tool_use_id, result))

        if not tool_results:
            # No tool calls => model claims it's done / can't proceed.
            if verbose:
                print(f"[step {step:03d}] no tool call; model stopped.", flush=True)
            break

        messages.append({"role": "user", "content": tool_results})

    if load_skills and posttask_learn and skill_manifest_entries:
        metrics["posttask_patch_attempted"] = True
        # Keep reflection payload compact and deterministic.
        tail_events = []
        try:
            ev_lines = paths.jsonl_path.read_text(encoding="utf-8").splitlines()
            for ln in ev_lines[-20:]:
                ev = json.loads(ln)
                tail_events.append(
                    {
                        "step": ev.get("step"),
                        "tool": ev.get("tool"),
                        "tool_input": ev.get("tool_input"),
                        "ok": ev.get("ok"),
                        "error": ev.get("error"),
                    }
                )
        except Exception:
            tail_events = []

        routed_refs = [e.skill_ref for e in routed_skill_entries]
        skill_texts: list[str] = []
        skill_digests: dict[str, str] = {}
        for ref in routed_refs[:3]:
            content, err = resolve_skill_content(skill_manifest_entries, ref)
            if err or content is None:
                continue
            digest = skill_digest(content)
            skill_digests[ref] = digest
            skill_texts.append(f"skill_ref: {ref}\nskill_digest: {digest}\n{content}")

        reflection_system = (
            "You are PostTaskHook for autonomous skill maintenance.\n"
            "Given task + tool trace + current skills, propose grounded updates.\n"
            "Return STRICT JSON only:\n"
            "{\n"
            '  "confidence": 0.0,\n'
            '  "skill_updates": [\n'
            "    {\n"
            '      "skill_ref": "...",\n'
            '      "skill_digest": "...",\n'
            '      "root_cause": "...",\n'
            '      "evidence_steps": [5, 8],\n'
            '      "replace_rules": [{"find":"...","replace":"..."}],\n'
            '      "append_bullets": ["..."]\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "Rules:\n"
            "- Prefer fixing/rewriting weak existing rules via replace_rules before appending new bullets.\n"
            "- Every update must include concrete root_cause and evidence_steps from provided events.\n"
            "- Every update must include exact skill_digest for the skill snapshot.\n"
            "- Do not repeat guidance already present in the skill.\n"
            "- Prefer generic reusable lessons over one-off coordinates, unless coordinates expose a repeated failure pattern.\n"
            "- Max 2 skills, max 3 bullets per skill.\n"
            "- Do not propose updates if signal is weak.\n"
        )
        reflection_user = (
            "TASK:\n"
            f"{task}\n\n"
            "METRICS:\n"
            f"{json.dumps(metrics, ensure_ascii=True)}\n\n"
            "EVENTS_TAIL:\n"
            f"{json.dumps(tail_events, ensure_ascii=True)}\n\n"
            "ROUTED_SKILLS:\n"
            f"{json.dumps(routed_refs, ensure_ascii=True)}\n\n"
            "READ_SKILL_REFS:\n"
            f"{json.dumps(sorted(read_skill_refs), ensure_ascii=True)}\n\n"
            "SKILL_DIGESTS:\n"
            f"{json.dumps(skill_digests, ensure_ascii=True)}\n\n"
            "SKILL_CONTENTS:\n"
            + "\n\n".join(skill_texts)
        )
        try:
            reflection = client.messages.create(
                model=cfg.model_decider,
                max_tokens=700,
                system=reflection_system,
                messages=[{"role": "user", "content": reflection_user}],
            )
            raw = ""
            for b in reflection.content:
                bd = b.model_dump() if hasattr(b, "model_dump") else b  # type: ignore[attr-defined]
                if isinstance(bd, dict) and bd.get("type") == "text":
                    raw += str(bd.get("text", ""))
            updates, confidence = parse_reflection_response(raw)
            valid_steps = {int(e.get("step")) for e in tail_events if isinstance(e.get("step"), int)}
            patch_result = apply_skill_updates(
                entries=skill_manifest_entries,
                updates=updates,
                confidence=confidence,
                min_confidence=0.7,
                valid_steps=valid_steps,
                required_skill_digests=skill_digests,
                allowed_skill_refs=read_skill_refs,
            )
            metrics["posttask_patch_applied"] = int(patch_result.get("applied", 0))
            write_event(
                paths.jsonl_path,
                {
                    "step": metrics["steps"],
                    "tool": "posttask_hook",
                    "tool_input": {"routed_refs": routed_refs},
                    "ok": True,
                    "error": None,
                    "output": patch_result,
                    "screenshot": None,
                    "usage": None,
                },
            )
        except Exception as exc:
            write_event(
                paths.jsonl_path,
                {
                    "step": metrics["steps"],
                    "tool": "posttask_hook",
                    "tool_input": {"routed_refs": routed_refs},
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "output": None,
                    "screenshot": None,
                    "usage": None,
                },
            )

    metrics["time_end"] = time.time()
    metrics["elapsed_s"] = metrics["time_end"] - metrics["time_start"]
    write_metrics(paths.metrics_path, metrics)

    return RunResult(messages=messages, metrics=metrics)
