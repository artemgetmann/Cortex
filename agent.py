from __future__ import annotations

import base64
import io
import json
import os
import re
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
from PIL import Image

from config import CortexConfig
from computer_use import ComputerTool, ToolResult
from fl_state import (
    EXTRACT_FL_STATE_TOOL_NAME,
    extract_fl_state_from_image,
    fl_state_tool_param,
    resolve_reference_images,
)
from fl_visual_judge import VisualJudgeResult, judge_fl_visual
from learning import generate_lessons, load_relevant_lessons, store_lessons
from memory import ensure_session, write_event, write_metrics
from run_eval import evaluate_drum_run
from self_improve import (
    SkillUpdate,
    apply_skill_updates,
    auto_promote_queued_candidates,
    parse_reflection_response,
    queue_skill_update_candidates,
    skill_digest,
)
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
- Use extract_fl_state to convert screenshots into structured UI facts before repeating zooms.
- Use app-specific skills for UI conventions and domain workflows.
- Keep the run safe: do not interact with anything outside FL Studio.
- Never use OS-level shortcuts: do not press Command+Q, Command+Tab, Command+W, Command+M, or anything intended to quit/switch apps.
"""


def _supports_computer_20251124(model: str) -> bool:
    """
    Map model id -> computer tool generation.

    Anthropic currently documents `computer_20251124` (zoom-enabled) for Opus
    4.6/4.5, while Sonnet 4.6/4.5 stay on `computer_20250124`.
    """
    model_id = model.strip().lower()
    return ("opus-4-6" in model_id) or ("opus-4-5" in model_id)


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
MAX_SAME_STEP_RETRIES = 2
LLM_BACKENDS = ("anthropic", "claude_print")
DEFAULT_LLM_BACKEND = "anthropic"


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


def _normalize_llm_backend(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in LLM_BACKENDS:
        raise ValueError(f"Unsupported llm_backend: {value!r}. Expected one of {LLM_BACKENDS}.")
    return normalized


def _clip_text(text: str, *, max_chars: int = 4000) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _render_message_history_for_claude_print(messages: list[dict[str, Any]]) -> str:
    """
    Flatten API-style block history into compact text for claude -p.

    Keep the history short to avoid turning each step into a huge prompt.
    """
    lines: list[str] = []
    for msg in messages[-12:]:
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
            btype = str(block.get("type", "")).strip().lower()
            if btype == "text":
                text = str(block.get("text", "")).strip()
                if text:
                    lines.append(f"TEXT: {text}")
            elif btype == "tool_use":
                tool_name = str(block.get("name", "")).strip()
                tool_input = json.dumps(block.get("input", {}), ensure_ascii=True, sort_keys=True)
                lines.append(f"TOOL_USE {tool_name}: {tool_input}")
            elif btype == "tool_result":
                tool_use_id = str(block.get("tool_use_id", "")).strip()
                is_error = bool(block.get("is_error", False))
                content = block.get("content")
                text_parts: list[str] = []
                has_image = False
                if isinstance(content, list):
                    for part in content:
                        if not isinstance(part, dict):
                            continue
                        ptype = str(part.get("type", "")).strip().lower()
                        if ptype == "text":
                            text_parts.append(str(part.get("text", "")))
                        elif ptype == "image":
                            has_image = True
                elif isinstance(content, str):
                    text_parts.append(content)
                merged = " ".join(part for part in text_parts if part).strip()
                if has_image:
                    merged = f"{merged} [screenshot-attached]".strip()
                lines.append(f"TOOL_RESULT {tool_use_id} error={is_error}: {merged}")
            else:
                lines.append(json.dumps(block, ensure_ascii=True, sort_keys=True))
        lines.append("")
    return "\n".join(lines).strip()


def _extract_latest_tool_result_image(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    """
    Return the latest tool_result image block as a compact JPEG image block.
    """
    for msg in reversed(messages):
        if str(msg.get("role")) != "user":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in reversed(content):
            if not (isinstance(block, dict) and str(block.get("type")) == "tool_result"):
                continue
            parts = block.get("content")
            if not isinstance(parts, list):
                continue
            for part in reversed(parts):
                if not (isinstance(part, dict) and str(part.get("type")) == "image"):
                    continue
                src = part.get("source", {})
                if not isinstance(src, dict):
                    continue
                data = src.get("data")
                media_type = str(src.get("media_type", "image/png")).strip() or "image/png"
                if not isinstance(data, str) or not data:
                    continue
                compact = _compact_image_block_for_prompt(data_b64=data, media_type=media_type)
                if compact is not None:
                    return compact
    return None


def _compact_image_block_for_prompt(*, data_b64: str, media_type: str) -> dict[str, Any] | None:
    """
    Downscale/compress screenshot blocks so claude -p prompt size stays tractable.
    """
    try:
        raw = base64.b64decode(data_b64.encode("ascii"), validate=True)
        with Image.open(io.BytesIO(raw)) as img:
            working = img.convert("RGB")
            working.thumbnail((640, 480))
            out = io.BytesIO()
            working.save(out, format="JPEG", quality=55, optimize=True)
            compact_b64 = base64.b64encode(out.getvalue()).decode("ascii")
    except Exception:
        return None
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": compact_b64,
        },
    }


def _extract_first_json_object(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        raise RuntimeError("claude -p returned empty output.")
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
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
    raise RuntimeError(f"claude -p output is not valid JSON object: {_clip_text(text, max_chars=600)}")


def _assistant_blocks_from_claude_print_payload(
    *,
    payload: dict[str, Any],
    allowed_tool_names: set[str],
) -> list[dict[str, Any]]:
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
                "id": f"toolu_cli_{uuid.uuid4().hex[:12]}_{idx}",
                "name": name,
                "input": tool_input,
            }
        )
    return blocks


def _create_executor_response_via_claude_print(
    *,
    model: str,
    system_blocks: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Run one FL executor turn via claude -p using stream-json input.

    We include the latest screenshot as a compact image block so the model
    still has visual grounding.
    """
    allowed_tool_names = {
        str(tool.get("name", "")).strip()
        for tool in tools
        if isinstance(tool, dict) and str(tool.get("name", "")).strip()
    }
    tools_for_prompt: list[dict[str, Any]] = []
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

    system_text = "\n\n".join(
        str(block.get("text", "")).strip()
        for block in system_blocks
        if isinstance(block, dict) and str(block.get("type", "")).strip() == "text"
    ).strip()
    history_text = _render_message_history_for_claude_print(messages)
    prompt = (
        "You are the planner for a tool-using FL Studio loop.\n"
        "Return exactly one JSON object with this shape:\n"
        "{\n"
        '  "assistant_text": "short reasoning",\n'
        '  "tool_calls": [{"name":"tool_name","input":{...}}]\n'
        "}\n"
        "Rules:\n"
        "- Use only listed tools.\n"
        "- Prefer one decisive tool call at a time.\n"
        "- tool_calls may be empty if task is complete.\n"
        "- input must satisfy tool input_schema.\n"
        "- Output strict JSON only (no markdown).\n\n"
        f"SYSTEM_PROMPT:\n{system_text}\n\n"
        f"TOOLS:\n{json.dumps(tools_for_prompt, ensure_ascii=True, indent=2, sort_keys=True)}\n\n"
        f"MESSAGE_HISTORY:\n{history_text}\n"
    )

    content_blocks: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    latest_image = _extract_latest_tool_result_image(messages)
    if latest_image is not None:
        content_blocks.append({"type": "text", "text": "LATEST_SCREENSHOT:"})
        content_blocks.append(latest_image)
    input_line = {
        "type": "user",
        "message": {
            "role": "user",
            "content": content_blocks,
        },
    }

    timeout_s = max(15, int(os.getenv("CORTEX_CLAUDE_PRINT_TIMEOUT_S", "120")))
    cmd = [
        "claude",
        "-p",
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        "--verbose",
        "--tools",
        "",
    ]
    if model.strip():
        cmd.extend(["--model", model.strip()])
    try:
        proc = subprocess.run(
            cmd,
            input=json.dumps(input_line, ensure_ascii=True) + "\n",
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"claude -p executor turn timed out after {timeout_s}s. "
            "Try increasing CORTEX_CLAUDE_PRINT_TIMEOUT_S or reducing max steps."
        ) from exc

    stdout = str(proc.stdout or "")
    stderr = str(proc.stderr or "")
    if proc.returncode != 0:
        raise RuntimeError(
            "claude -p executor turn failed "
            f"(code={proc.returncode}): {_clip_text(stderr or stdout, max_chars=800)}"
        )

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
    if not result_text:
        raise RuntimeError(f"claude -p produced no result payload: {_clip_text(stdout, max_chars=800)}")
    payload = _extract_first_json_object(result_text)
    assistant_blocks = _assistant_blocks_from_claude_print_payload(
        payload=payload,
        allowed_tool_names=allowed_tool_names,
    )
    usage_payload = {
        "backend": "claude_print",
        "model": model,
        "stdout_chars": len(stdout),
        "stderr_chars": len(stderr),
        **usage_payload,
    }
    return assistant_blocks, usage_payload


def _save_png_b64(session_dir: Path, *, name: str, b64: str) -> Path:
    out = session_dir / name
    out.write_bytes(base64.b64decode(b64))
    return out


def _image_block_from_file(path: Path) -> dict[str, Any] | None:
    try:
        data = base64.b64encode(path.read_bytes()).decode("ascii")
    except Exception:
        return None
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": data,
        },
    }


def _select_reflection_screenshots(
    events: list[dict[str, Any]],
    *,
    max_images: int = 3,
) -> list[tuple[int, Path]]:
    candidates: list[tuple[int, Path]] = []
    for ev in events:
        shot = ev.get("screenshot")
        step = ev.get("step")
        if not isinstance(shot, str) or not shot:
            continue
        if not isinstance(step, int):
            continue
        p = Path(shot)
        if p.exists():
            candidates.append((step, p))
    if not candidates:
        return []

    # Pick representative frames: early, middle, late.
    picks: list[tuple[int, Path]] = []
    indexes = sorted({0, len(candidates) // 2, len(candidates) - 1})
    for idx in indexes:
        picks.append(candidates[idx])
    # Keep stable ordering and max bound.
    seen: set[str] = set()
    deduped: list[tuple[int, Path]] = []
    for step, p in picks:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((step, p))
    return deduped[:max_images]


def _load_fl_reference_snippet(*, max_chars: int = 1600) -> str:
    p = Path("docs/FL-STUDIO-REFERENCE.md")
    if not p.exists():
        return ""
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        return ""
    text = " ".join(text.split())
    return text[:max_chars]


def _read_session_events(events_path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        lines = events_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return events
    for line in lines:
        try:
            parsed = json.loads(line)
        except Exception:
            continue
        if isinstance(parsed, dict):
            events.append(parsed)
    return events


def _latest_screenshot_from_events(events: list[dict[str, Any]]) -> Path | None:
    latest_step = -1
    latest_path: Path | None = None
    for ev in events:
        raw_path = ev.get("screenshot")
        raw_step = ev.get("step")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        if not isinstance(raw_step, int):
            continue
        path = Path(raw_path)
        if not path.exists():
            continue
        if raw_step >= latest_step:
            latest_step = raw_step
            latest_path = path
    return latest_path


def _build_fallback_updates(
    *,
    eval_result: dict[str, Any],
    read_skill_refs: set[str],
    skill_digests: dict[str, str],
) -> tuple[list[SkillUpdate], float]:
    reasons = eval_result.get("reasons")
    if not isinstance(reasons, list):
        return [], 0.0
    reason_set = {r for r in reasons if isinstance(r, str)}
    if not reason_set:
        return [], 0.0

    target_ref = "fl-studio/drum-pattern"
    if target_ref not in read_skill_refs:
        return [], 0.0
    digest = skill_digests.get(target_ref, "")
    if not digest:
        return [], 0.0

    evidence_steps: list[int] = []
    clicks = eval_result.get("clicks", [])
    if isinstance(clicks, list):
        for item in clicks[:4]:
            if isinstance(item, dict):
                s = item.get("step")
                if isinstance(s, int) and s > 0:
                    evidence_steps.append(s)
    if not evidence_steps:
        evidence_steps = [1]

    bullets: list[str] = []
    replace_rules = []
    root_parts: list[str] = []

    if "selector_zone_misclick" in reason_set:
        root_parts.append("First step clicks entered selector strip instead of the step-button band.")
        bullets.append(
            "When clicking kick steps, avoid the selector strip near channel name; if Hint Bar shows Select/UpDown, move right and retry."
        )
    if "inspection_loop" in reason_set:
        root_parts.append("Run spent too many inspection actions before decisive clicks.")
        replace_rules.append(
            {
                "find": "Do not spam zoom on the step row. At most one zoom is allowed before the click sequence.",
                "replace": "Do at most one zoom before the click sequence; then execute the four clicks without additional zoom.",
            }
        )
    if "insufficient_step_clicks" in reason_set:
        root_parts.append("Run ended before four kick-step clicks were completed.")
        bullets.append("Do not stop early: complete exactly four kick-step clicks (1,5,9,13) before any final verification.")

    if not bullets and not replace_rules:
        return [], 0.0

    rr_objs = []
    from self_improve import ReplaceRule  # local import to avoid widening global import list

    for rr in replace_rules[:2]:
        rr_objs.append(ReplaceRule(find=rr["find"], replace=rr["replace"]))

    update = SkillUpdate(
        skill_ref=target_ref,
        skill_digest=digest,
        root_cause=" ".join(root_parts)[:400],
        evidence_steps=sorted(set(evidence_steps))[:6],
        replace_rules=rr_objs,
        append_bullets=bullets[:3],
    )
    return [update], 0.8


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
    posttask_mode: str = "direct",
    llm_backend: str = DEFAULT_LLM_BACKEND,
    verbose: bool = False,
) -> RunResult:
    llm_backend = _normalize_llm_backend(llm_backend)
    api_key = str(getattr(cfg, "anthropic_api_key", "") or "").strip()
    client: Any | None = None
    if llm_backend == "anthropic":
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required when llm_backend=anthropic.")
        client = anthropic.Anthropic(api_key=api_key, max_retries=3)

    # Tool version + beta flag must match the chosen model's computer-use support.
    # Do not rely on "heavy vs decider" naming because users may run Sonnet as the
    # primary model for speed/cost.
    if _supports_computer_20251124(model):
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
    if posttask_learn:
        lessons_text, lessons_loaded = load_relevant_lessons(task, max_lessons=10, max_sessions=5)
    else:
        lessons_text, lessons_loaded = ("No prior lessons loaded.", 0)
    lessons_system_block: dict[str, Any] = {"type": "text", "text": lessons_text}
    skill_usage_block: dict[str, Any] = {
        "type": "text",
        "text": (
            "Skills policy:\n"
            "- You only have skill titles and descriptions at start.\n"
            "- If a listed skill may help, call read_skill with that exact skill_ref to fetch full steps.\n"
            "- Do not assume full skill contents without calling read_skill.\n"
            "- Keep read_skill calls targeted; avoid reading every skill."
            "\n"
            "State policy:\n"
            + (
                "- Use extract_fl_state after screenshot when UI is ambiguous.\n"
                "- Prefer extracting structured state (rows/active steps) over repeated zoom loops.\n"
                if llm_backend == "anthropic"
                else "- extract_fl_state is unavailable in this run; use screenshot + direct action/verification.\n"
            )
        ),
    }
    system_blocks = [base_system_block, skills_system_block, lessons_system_block, skill_usage_block]

    tools: list[dict[str, Any]] = [computer.to_tool_param()]
    if llm_backend == "anthropic":
        tools.append(fl_state_tool_param())
    if load_skills:
        tools.append(_read_skill_tool_param())

    betas = [computer_beta]
    if cfg.enable_prompt_caching:
        betas.append(PROMPT_CACHING_BETA_FLAG)
        # Cache after stable context blocks so repeated runs can reuse prefix tokens.
        skills_system_block["cache_control"] = {"type": "ephemeral"}
        lessons_system_block["cache_control"] = {"type": "ephemeral"}
    # Anthropic limit: max 4 cache_control blocks total in a request.
    # We currently use 2 on system blocks (skills + lessons), so user-turn cache
    # breakpoints must be capped to keep requests valid.
    system_cache_blocks = int("cache_control" in skills_system_block) + int("cache_control" in lessons_system_block)
    user_cache_breakpoints = max(0, 4 - system_cache_blocks)
    # Reduce screenshot/tool payload overhead when supported.
    # If unsupported by the model, the API will 400; we'll disable if that happens.
    betas.append(cfg.token_efficient_tools_beta)

    metrics: dict[str, Any] = {
        "session_id": session_id,
        "task": task,
        "model": model,
        "llm_backend": llm_backend,
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
        "posttask_candidates_queued": 0,
        "posttask_skip_reason": None,
        "lessons_loaded": lessons_loaded,
        "lessons_generated": 0,
        "auto_promotion_applied": 0,
        "auto_promotion_reason": None,
        "eval_passed": None,
        "eval_score": None,
        "eval_reasons": [],
        "eval_final_verdict": "unknown",
        "eval_source": "none",
        "eval_disagreement": False,
        "eval_det_passed": None,
        "eval_det_score": None,
        "eval_det_reasons": [],
        "judge_model": cfg.model_visual_judge,
        "judge_passed": None,
        "judge_score": None,
        "judge_confidence": None,
        "judge_reasons": [],
        "judge_reference_images": [],
        "judge_observed_steps": [],
        "usage": [],
    }
    # Hard guardrail for Opus path: stop inspection loops and force decisive actions.
    non_productive_streak = 0
    loop_guard_enabled = computer_api_type == "computer_20251124"
    read_skill_refs: set[str] = set()

    step = 1
    same_step_retries = 0
    while step <= max_steps:
        metrics["steps"] = step
        if cfg.enable_prompt_caching and llm_backend == "anthropic":
            _inject_prompt_caching(messages, breakpoints=user_cache_breakpoints)

        if llm_backend == "anthropic":
            if client is None:
                raise RuntimeError("Anthropic client unavailable while llm_backend=anthropic.")
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
            assistant_blocks = [b.model_dump() for b in resp.content]  # type: ignore[attr-defined]
        else:
            assistant_blocks, usage = _create_executor_response_via_claude_print(
                model=model,
                system_blocks=system_blocks,
                tools=tools,
                messages=messages,
            )
        metrics["usage"].append(usage)
        messages.append({"role": "assistant", "content": assistant_blocks})

        tool_results: list[dict[str, Any]] = []
        retry_same_step = False
        decisive_action_succeeded = False

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
                        retry_same_step = True
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
                        decisive_action_succeeded = True

                except Exception as e:
                    # Don't crash the loop on unexpected local tool errors; surface it to the model.
                    result = ToolResult(error=f"Local tool exception: {type(e).__name__}: {e}")
                if result.is_error():
                    metrics["tool_errors"] += 1
            elif tool_name == EXTRACT_FL_STATE_TOOL_NAME:
                tool_in = tool_input if isinstance(tool_input, dict) else {}
                goal = str(tool_in.get("goal", "")).strip()
                task_hint = str(tool_in.get("task_hint", "")).strip() or task
                if llm_backend != "anthropic" or client is None:
                    result = ToolResult(error="extract_fl_state is unavailable when llm_backend=claude_print")
                    metrics["tool_errors"] += 1
                else:
                    try:
                        shot = computer.run({"action": "screenshot"})
                        if shot.is_error() or not shot.base64_image_png:
                            result = ToolResult(error=shot.error or "extract_fl_state could not capture screenshot")
                            metrics["tool_errors"] += 1
                        else:
                            state = extract_fl_state_from_image(
                                client=client,
                                model=cfg.model_decider,
                                screenshot_b64=shot.base64_image_png,
                                goal=goal,
                                task_hint=task_hint,
                            )
                            result = ToolResult(
                                output=json.dumps(state, ensure_ascii=True),
                                base64_image_png=shot.base64_image_png,
                            )
                    except Exception as e:
                        result = ToolResult(error=f"extract_fl_state exception: {type(e).__name__}: {e}")
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
        if retry_same_step and not decisive_action_succeeded and same_step_retries < MAX_SAME_STEP_RETRIES:
            same_step_retries += 1
            if verbose:
                print(
                    f"[step {step:03d}] governor retry without step burn ({same_step_retries}/{MAX_SAME_STEP_RETRIES})",
                    flush=True,
                )
            continue
        same_step_retries = 0
        step += 1

    # End-of-run evaluation: deterministic contract + independent visual judge.
    all_events: list[dict[str, Any]] = _read_session_events(paths.jsonl_path)
    tail_events: list[dict[str, Any]] = []
    for ev in all_events[-20:]:
        tail_events.append(
            {
                "step": ev.get("step"),
                "tool": ev.get("tool"),
                "tool_input": ev.get("tool_input"),
                "ok": ev.get("ok"),
                "error": ev.get("error"),
            }
        )

    drum_eval = evaluate_drum_run(task, all_events).to_dict()
    det_passed = bool(drum_eval.get("passed"))
    try:
        det_score = float(drum_eval.get("score", 0.0))
    except (TypeError, ValueError):
        det_score = 0.0
    det_reasons = drum_eval.get("reasons")
    if not isinstance(det_reasons, list):
        det_reasons = []

    visual_judge: VisualJudgeResult | None = None
    final_shot = _latest_screenshot_from_events(all_events)
    if final_shot is not None and llm_backend == "anthropic" and client is not None:
        try:
            screenshot_b64 = base64.b64encode(final_shot.read_bytes()).decode("ascii")
            judge_refs = resolve_reference_images()
            visual_judge = judge_fl_visual(
                client=client,
                model=cfg.model_visual_judge,
                final_screenshot_b64=screenshot_b64,
                task=task,
                rubric=(
                    "Pass only if FL Studio kick row uses 4-on-the-floor pattern with active steps 1,5,9,13 "
                    "and without obvious step-index mismatches."
                ),
                reference_images=judge_refs,
            )
            write_event(
                paths.jsonl_path,
                {
                    "step": metrics["steps"],
                    "tool": "visual_judge",
                    "tool_input": {
                        "model": cfg.model_visual_judge,
                        "final_screenshot": str(final_shot),
                        "reference_images": [str(p) for p in judge_refs],
                    },
                    "ok": True,
                    "error": None,
                    "output": visual_judge.to_dict(),
                    "screenshot": str(final_shot),
                    "usage": None,
                },
            )
        except Exception as exc:
            write_event(
                paths.jsonl_path,
                {
                    "step": metrics["steps"],
                    "tool": "visual_judge",
                    "tool_input": {"model": cfg.model_visual_judge},
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "output": None,
                    "screenshot": str(final_shot),
                    "usage": None,
                },
            )
    elif final_shot is not None and llm_backend != "anthropic":
        write_event(
            paths.jsonl_path,
            {
                "step": metrics["steps"],
                "tool": "visual_judge",
                "tool_input": {"model": cfg.model_visual_judge},
                "ok": False,
                "error": "visual_judge skipped: llm_backend=claude_print",
                "output": None,
                "screenshot": str(final_shot),
                "usage": None,
            },
        )

    final_verdict = "pass" if det_passed else "fail"
    final_score = det_score
    final_reasons = list(det_reasons)
    eval_source = "deterministic"
    eval_disagreement = False
    if llm_backend != "anthropic":
        eval_source = "deterministic_no_judge"
        final_reasons.extend(["visual_judge_skipped_llm_backend"])
    if visual_judge is not None:
        judge_unparseable = any(str(r) == "visual_judge_unparseable" for r in visual_judge.reasons)
        if judge_unparseable:
            # If judge output is structurally invalid, do not let parser noise override
            # objective deterministic signals. Keep judge diagnostics in metrics.
            eval_source = "deterministic_fallback"
            final_reasons.extend(["judge_unparseable_fallback"])
        else:
            eval_source = "hybrid"
            if bool(visual_judge.passed) == bool(det_passed):
                final_verdict = "pass" if det_passed else "fail"
                final_score = round((det_score + float(visual_judge.score)) / 2.0, 3)
                if visual_judge.reasons:
                    final_reasons.extend([f"judge:{r}" for r in visual_judge.reasons])
            else:
                final_verdict = "uncertain"
                final_score = round(min(det_score, float(visual_judge.score)), 3)
                eval_disagreement = True
                final_reasons.extend(
                    [
                        "judge_disagreement",
                        f"deterministic_passed={det_passed}",
                        f"visual_judge_passed={visual_judge.passed}",
                    ]
                )

    metrics["eval_det_passed"] = det_passed
    metrics["eval_det_score"] = round(det_score, 3)
    metrics["eval_det_reasons"] = det_reasons
    metrics["eval_source"] = eval_source
    metrics["eval_disagreement"] = eval_disagreement
    metrics["eval_final_verdict"] = final_verdict
    metrics["eval_passed"] = final_verdict == "pass"
    metrics["eval_score"] = round(final_score, 3)
    metrics["eval_reasons"] = final_reasons[:12]
    if visual_judge is not None:
        metrics["judge_passed"] = visual_judge.passed
        metrics["judge_score"] = visual_judge.score
        metrics["judge_confidence"] = visual_judge.confidence
        metrics["judge_reasons"] = visual_judge.reasons
        metrics["judge_reference_images"] = visual_judge.reference_images_used
        metrics["judge_observed_steps"] = visual_judge.observed_active_steps

    if load_skills and posttask_learn and skill_manifest_entries and llm_backend == "anthropic":
        if client is None:
            raise RuntimeError("posttask_learn requires Anthropic client.")
        metrics["posttask_patch_attempted"] = True
        # Keep reflection payload compact and deterministic.
        eval_passed = bool(metrics.get("eval_passed"))
        try:
            eval_score = float(metrics.get("eval_score", 0.0))
        except (TypeError, ValueError):
            eval_score = 0.0

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

        reference_doc = _load_fl_reference_snippet()
        reflection_system = (
            "You are PostTaskHook for autonomous skill maintenance.\n"
            "Given task + tool trace + screenshots + current skills + reference docs, propose grounded updates.\n"
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
            "- Use DETERMINISTIC_EVAL as the primary failure signal. If eval says passed=true, return no updates.\n"
            "- Use screenshot evidence and reference docs to justify root cause and proposed rules.\n"
            "- Max 2 skills, max 3 bullets per skill.\n"
            "- Do not propose updates if signal is weak.\n"
        )
        reflection_user = (
            "TASK:\n"
            f"{task}\n\n"
            "METRICS:\n"
            f"{json.dumps(metrics, ensure_ascii=True)}\n\n"
            "DETERMINISTIC_EVAL:\n"
            f"{json.dumps(drum_eval, ensure_ascii=True)}\n\n"
            "VISUAL_JUDGE:\n"
            f"{json.dumps(visual_judge.to_dict() if visual_judge is not None else {}, ensure_ascii=True)}\n\n"
            "FINAL_EVAL:\n"
            f"{json.dumps({'verdict': metrics.get('eval_final_verdict'), 'passed': metrics.get('eval_passed'), 'score': metrics.get('eval_score')}, ensure_ascii=True)}\n\n"
            "EVENTS_TAIL:\n"
            f"{json.dumps(tail_events, ensure_ascii=True)}\n\n"
            "ROUTED_SKILLS:\n"
            f"{json.dumps(routed_refs, ensure_ascii=True)}\n\n"
            "READ_SKILL_REFS:\n"
            f"{json.dumps(sorted(read_skill_refs), ensure_ascii=True)}\n\n"
            "SKILL_DIGESTS:\n"
            f"{json.dumps(skill_digests, ensure_ascii=True)}\n\n"
            "REFERENCE_DOC_SNIPPET:\n"
            f"{reference_doc}\n\n"
            "SKILL_CONTENTS:\n"
            + "\n\n".join(skill_texts)
        )
        try:
            # Lessons are append-only memory: generated only for imperfect outcomes.
            if (not eval_passed) or eval_score < 1.0:
                lessons = generate_lessons(
                    client=client,
                    model=cfg.model_critic,
                    session_id=session_id,
                    task=task,
                    eval_result=drum_eval,
                    events_tail=tail_events,
                    skill_refs_used=routed_refs,
                )
                metrics["lessons_generated"] = store_lessons(lessons)
            else:
                metrics["lessons_generated"] = 0

            reflection_content: list[dict[str, Any]] = [{"type": "text", "text": reflection_user}]
            shot_labels: list[str] = []
            for step_id, shot_path in _select_reflection_screenshots(all_events, max_images=3):
                blk = _image_block_from_file(shot_path)
                if blk is None:
                    continue
                shot_labels.append(f"step-{step_id}: {shot_path}")
                reflection_content.append(blk)
            if shot_labels:
                reflection_content.insert(
                    1,
                    {
                        "type": "text",
                        "text": "SCREENSHOTS_INCLUDED:\n" + "\n".join(shot_labels),
                    },
                )

            reflection = client.messages.create(
                model=cfg.model_critic,
                max_tokens=700,
                system=reflection_system,
                messages=[{"role": "user", "content": reflection_content}],
            )
            raw = ""
            for b in reflection.content:
                bd = b.model_dump() if hasattr(b, "model_dump") else b  # type: ignore[attr-defined]
                if isinstance(bd, dict) and bd.get("type") == "text":
                    raw += str(bd.get("text", ""))
            updates, confidence = parse_reflection_response(raw)
            if (not updates) and (not eval_passed):
                fallback_updates, fallback_conf = _build_fallback_updates(
                    eval_result=drum_eval,
                    read_skill_refs=read_skill_refs,
                    skill_digests=skill_digests,
                )
                if fallback_updates:
                    updates = fallback_updates
                    confidence = max(confidence, fallback_conf)
            valid_steps = {int(e.get("step")) for e in tail_events if isinstance(e.get("step"), int)}
            if posttask_mode == "candidate":
                patch_result = queue_skill_update_candidates(
                    updates=updates,
                    confidence=confidence,
                    session_id=session_id,
                    required_skill_digests=skill_digests,
                    allowed_skill_refs=read_skill_refs,
                    min_confidence=0.7,
                    evaluation=drum_eval,
                )
                metrics["posttask_candidates_queued"] = int(patch_result.get("queued", 0))
            else:
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

            if posttask_mode == "candidate":
                promotion = auto_promote_queued_candidates(
                    entries=skill_manifest_entries,
                    min_runs=3,
                    min_delta=0.2,
                    max_sessions=8,
                )
                metrics["auto_promotion_applied"] = int(promotion.get("applied", 0))
                metrics["auto_promotion_reason"] = promotion.get("reason")
                write_event(
                    paths.jsonl_path,
                    {
                        "step": metrics["steps"],
                        "tool": "promotion_gate",
                        "tool_input": {"mode": "candidate"},
                        "ok": bool(promotion.get("applied", 0) > 0),
                        "error": None if promotion.get("applied", 0) else str(promotion.get("reason")),
                        "output": promotion,
                        "screenshot": None,
                        "usage": None,
                    },
                )
            write_event(
                paths.jsonl_path,
                {
                    "step": metrics["steps"],
                    "tool": "posttask_hook",
                    "tool_input": {"routed_refs": routed_refs, "mode": posttask_mode},
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
                    "tool_input": {"routed_refs": routed_refs, "mode": posttask_mode},
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "output": None,
                    "screenshot": None,
                    "usage": None,
                },
            )
    elif load_skills and posttask_learn and llm_backend != "anthropic":
        metrics["posttask_patch_attempted"] = False
        metrics["posttask_skip_reason"] = "llm_backend"
        write_event(
            paths.jsonl_path,
            {
                "step": metrics["steps"],
                "tool": "posttask_hook",
                "tool_input": {"mode": posttask_mode},
                "ok": False,
                "error": "posttask_hook skipped: llm_backend=claude_print",
                "output": None,
                "screenshot": None,
                "usage": None,
            },
        )

    metrics["time_end"] = time.time()
    metrics["elapsed_s"] = metrics["time_end"] - metrics["time_start"]
    write_metrics(paths.metrics_path, metrics)

    return RunResult(messages=messages, metrics=metrics)
