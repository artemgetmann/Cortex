from __future__ import annotations

import base64
import io
import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any

from PIL import Image
from claude_print_runtime import (
    build_claude_print_env,
    clip_text as _clip_text,
    extract_stream_json_result,
    normalize_claude_print_effort,
    resolve_claude_print_model,
)


def _extract_system_text(system: Any) -> str:
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


def _compact_image_block(*, data_b64: str, media_type: str) -> dict[str, Any] | None:
    # Keep image attachments small to avoid ballooning claude -p prompt size.
    try:
        raw = base64.b64decode(data_b64.encode("ascii"), validate=True)
        with Image.open(io.BytesIO(raw)) as img:
            normalized = img.convert("RGB")
            normalized.thumbnail((768, 576))
            out = io.BytesIO()
            normalized.save(out, format="JPEG", quality=58, optimize=True)
            compact = base64.b64encode(out.getvalue()).decode("ascii")
    except Exception:
        return None
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": compact,
        },
    }


def _render_history_and_images(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    lines: list[str] = []
    images: list[dict[str, Any]] = []

    for msg in messages[-16:]:
        role = str(msg.get("role", "user")).strip() or "user"
        lines.append(f"ROLE: {role}")
        content = msg.get("content")
        if not isinstance(content, list):
            text = str(content or "").strip()
            if text:
                lines.append(f"TEXT: {_clip_text(text, max_chars=800)}")
            lines.append("")
            continue

        for block in content:
            if not isinstance(block, dict):
                continue
            btype = str(block.get("type", "")).strip().lower()
            if btype == "text":
                text = str(block.get("text", "")).strip()
                if text:
                    lines.append(f"TEXT: {_clip_text(text, max_chars=1200)}")
            elif btype == "tool_use":
                name = str(block.get("name", "")).strip()
                payload = json.dumps(block.get("input", {}), ensure_ascii=True, sort_keys=True)
                lines.append(f"TOOL_USE {name}: {_clip_text(payload, max_chars=1000)}")
            elif btype == "tool_result":
                tool_use_id = str(block.get("tool_use_id", "")).strip()
                is_error = bool(block.get("is_error", False))
                result_content = block.get("content")
                fragments: list[str] = []
                if isinstance(result_content, list):
                    for part in result_content:
                        if not isinstance(part, dict):
                            continue
                        ptype = str(part.get("type", "")).strip().lower()
                        if ptype == "text":
                            fragments.append(str(part.get("text", "")).strip())
                        elif ptype == "image":
                            src = part.get("source", {})
                            if not isinstance(src, dict):
                                continue
                            data = src.get("data")
                            if not isinstance(data, str) or not data:
                                continue
                            media_type = str(src.get("media_type", "image/png")).strip() or "image/png"
                            compact = _compact_image_block(data_b64=data, media_type=media_type)
                            if compact is not None and len(images) < 6:
                                images.append(compact)
                elif isinstance(result_content, str):
                    fragments.append(result_content.strip())
                merged = " ".join(fragment for fragment in fragments if fragment).strip()
                lines.append(
                    f"TOOL_RESULT {tool_use_id} error={is_error}: {_clip_text(merged, max_chars=1200)}"
                )
            elif btype == "image":
                src = block.get("source", {})
                if not isinstance(src, dict):
                    continue
                data = src.get("data")
                if not isinstance(data, str) or not data:
                    continue
                media_type = str(src.get("media_type", "image/png")).strip() or "image/png"
                compact = _compact_image_block(data_b64=data, media_type=media_type)
                if compact is not None and len(images) < 6:
                    images.append(compact)
            else:
                payload = json.dumps(block, ensure_ascii=True, sort_keys=True)
                lines.append(f"BLOCK: {_clip_text(payload, max_chars=1200)}")
        lines.append("")

    return "\n".join(lines).strip(), images


@dataclass(frozen=True)
class _UsageWrapper:
    payload: dict[str, Any]

    def model_dump(self) -> dict[str, Any]:
        return dict(self.payload)


@dataclass(frozen=True)
class _TextBlock:
    text: str

    def model_dump(self) -> dict[str, Any]:
        return {"type": "text", "text": self.text}


@dataclass(frozen=True)
class ClaudePrintResponse:
    content: list[_TextBlock]
    usage: _UsageWrapper


class _MessagesAPI:
    def __init__(self, *, default_effort: str | None = None) -> None:
        self._default_effort = default_effort

    def create(
        self,
        *,
        model: str,
        max_tokens: int = 0,
        system: Any = "",
        messages: list[dict[str, Any]] | None = None,
        **_: Any,
    ) -> ClaudePrintResponse:
        # max_tokens is accepted for interface parity with Anthropic client,
        # but claude -p does not use this setting directly.
        del max_tokens

        requested_model, effective_model = resolve_claude_print_model(
            model,
            fallback_model="claude-opus-4-6",
        )
        requested_effort = normalize_claude_print_effort(self._default_effort, default="high")

        system_text = _extract_system_text(system)
        history_text, image_blocks = _render_history_and_images(messages or [])
        prompt = (
            "You are handling one model response turn.\n"
            "Follow SYSTEM_PROMPT and MESSAGE_HISTORY exactly.\n"
            "If SYSTEM_PROMPT requests strict JSON output, return strict JSON only.\n\n"
            f"SYSTEM_PROMPT:\n{system_text}\n\n"
            f"MESSAGE_HISTORY:\n{history_text}\n"
        )
        content_blocks: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if image_blocks:
            content_blocks.append(
                {
                    "type": "text",
                    "text": "ATTACHED_IMAGES_FROM_HISTORY:",
                }
            )
            content_blocks.extend(image_blocks)

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
            "--effort",
            requested_effort,
            "--model",
            effective_model,
        ]
        cmd_env = build_claude_print_env()

        try:
            proc = subprocess.run(
                cmd,
                input=json.dumps(input_line, ensure_ascii=True) + "\n",
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
                env=cmd_env,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"claude -p timed out after {timeout_s}s") from exc

        stdout = str(proc.stdout or "")
        stderr = str(proc.stderr or "")
        if proc.returncode != 0:
            raise RuntimeError(
                "claude -p call failed "
                f"(code={proc.returncode}): {_clip_text(stderr or stdout, max_chars=800)}"
            )

        result_text, usage_payload = extract_stream_json_result(stdout)
        if not result_text:
            raise RuntimeError("claude -p returned no result payload")

        usage_payload = {
            "backend": "claude_print",
            "model": effective_model,
            "requested_model": requested_model,
            "effort": requested_effort,
            "stdout_chars": len(stdout),
            "stderr_chars": len(stderr),
            **usage_payload,
        }
        return ClaudePrintResponse(
            content=[_TextBlock(text=result_text)],
            usage=_UsageWrapper(payload=usage_payload),
        )


class ClaudePrintClient:
    def __init__(self, *, default_effort: str | None = None) -> None:
        self.messages = _MessagesAPI(default_effort=default_effort)
