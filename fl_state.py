from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any


EXTRACT_FL_STATE_TOOL_NAME = "extract_fl_state"
DEFAULT_CONTRACT_PATH = Path("skills/fl-studio/drum-pattern/CONTRACT.json")


def fl_state_tool_param() -> dict[str, Any]:
    return {
        "name": EXTRACT_FL_STATE_TOOL_NAME,
        "description": (
            "Extract structured FL Studio UI state from a screenshot. "
            "Use to identify Channel Rack rows, step-grid geometry, and active pattern steps."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "Optional intent, e.g. 'verify kick row steps 1/5/9/13'.",
                },
                "task_hint": {
                    "type": "string",
                    "description": "Optional task context for state extraction.",
                },
            },
            "additionalProperties": False,
        },
    }


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if not text:
        return {}
    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _image_block_from_path(path: Path) -> dict[str, Any] | None:
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except Exception:
        return None
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": encoded,
        },
    }


def _contract_reference_images(contract_path: Path = DEFAULT_CONTRACT_PATH) -> list[Path]:
    if not contract_path.exists():
        return []
    try:
        raw = json.loads(contract_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    refs = raw.get("reference_images", [])
    if not isinstance(refs, list):
        return []
    out: list[Path] = []
    for item in refs:
        if not isinstance(item, str):
            continue
        p = Path(item).expanduser()
        if not p.is_absolute():
            p = (contract_path.parent / p).resolve()
        if p.exists():
            out.append(p)
    return out[:3]


def _resolve_reference_images() -> list[Path]:
    out: list[Path] = []
    env_path = os.getenv("CORTEX_FL_REFERENCE_IMAGE", "").strip()
    if env_path:
        p = Path(env_path).expanduser()
        if p.exists():
            # Explicit user-provided reference is authoritative for demo runs.
            # Avoid mixing unrelated fallback screenshots when this is set.
            return [p]
    for p in _contract_reference_images():
        if p not in out:
            out.append(p)
    if out:
        # Contract references are intentionally curated; prefer them over generic fallback.
        return out[:3]
    downloads_dir = Path.home() / "Downloads"
    if downloads_dir.exists():
        candidates = sorted(
            downloads_dir.glob("Screenshot*.png"),
            key=lambda p: p.stat().st_mtime if p.exists() else 0.0,
            reverse=True,
        )
        for p in candidates[:2]:
            if p.exists() and p not in out:
                out.append(p)
    return out[:3]


def resolve_reference_images() -> list[Path]:
    """
    Public helper for any FL vision component that needs the same reference set.
    """
    return _resolve_reference_images()


def _normalize_state(raw: dict[str, Any]) -> dict[str, Any]:
    channel_rack_visible = bool(raw.get("channel_rack_visible", False))
    grid = raw.get("grid")
    rows = raw.get("rows")
    kick = raw.get("kick_row_guess")
    four = raw.get("four_on_floor")

    if not isinstance(grid, dict):
        grid = {}
    if not isinstance(rows, list):
        rows = []
    if not isinstance(kick, dict):
        kick = {}
    if not isinstance(four, dict):
        four = {}

    return {
        "channel_rack_visible": channel_rack_visible,
        "grid": grid,
        "rows": [r for r in rows if isinstance(r, dict)][:16],
        "kick_row_guess": kick,
        "four_on_floor": four,
    }


def extract_fl_state_from_image(
    *,
    client: Any,
    model: str,
    screenshot_b64: str,
    goal: str = "",
    task_hint: str = "",
) -> dict[str, Any]:
    """
    Vision-first state extraction for FL Studio.

    We intentionally request structured state (rows/grid/active steps) instead of
    free-form prose so the agent can plan from machine-readable UI facts.
    """
    system = (
        "You are a UI state extractor for FL Studio screenshots.\n"
        "Return STRICT JSON object only.\n"
        "Do not include markdown fences.\n"
        "Schema:\n"
        "{\n"
        '  "channel_rack_visible": true|false,\n'
        '  "grid": {"x_min": int|null, "x_max": int|null, "y_min": int|null, "y_max": int|null, "step_centers_x": [int], "confidence": 0.0},\n'
        '  "rows": [{"index": int, "label": string, "y_center": int|null, "active_steps": [int], "confidence": 0.0}],\n'
        '  "kick_row_guess": {"index": int|null, "label": string, "confidence": 0.0, "reason": string},\n'
        '  "four_on_floor": {"target_steps":[1,5,9,13], "active_match": true|false, "missing_steps":[int], "extra_steps":[int], "confidence": 0.0}\n'
        "}\n"
        "Rules:\n"
        "- Step numbering is 1..16 from left to right.\n"
        "- Treat label variants as equivalent: Kick, 808 Kick, BD, Bass Drum.\n"
        "- Confidence must be conservative if uncertain.\n"
    )

    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"GOAL: {goal or 'extract state'}\n"
                f"TASK_HINT: {task_hint or '-'}\n"
                "PRIMARY_SCREENSHOT follows."
            ),
        },
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": screenshot_b64,
            },
        },
    ]

    ref_paths = _resolve_reference_images()
    if ref_paths:
        content.append(
            {
                "type": "text",
                "text": (
                    "REFERENCE_EXAMPLES follow. Use them for visual grounding only; "
                    "do not require exact pixel match."
                ),
            }
        )
        for ref in ref_paths:
            blk = _image_block_from_path(ref)
            if blk is not None:
                content.append({"type": "text", "text": f"reference_image={ref}"})
                content.append(blk)

    resp = client.messages.create(
        model=model,
        max_tokens=900,
        system=system,
        messages=[{"role": "user", "content": content}],
    )
    raw = ""
    for b in resp.content:
        bd = b.model_dump() if hasattr(b, "model_dump") else b  # type: ignore[attr-defined]
        if isinstance(bd, dict) and bd.get("type") == "text":
            raw += str(bd.get("text", ""))
    parsed = _extract_json_object(raw)
    if not parsed:
        return {
            "channel_rack_visible": False,
            "grid": {},
            "rows": [],
            "kick_row_guess": {},
            "four_on_floor": {"target_steps": [1, 5, 9, 13], "active_match": False},
            "error": "state_extraction_parse_failed",
            "raw": raw[:2000],
        }
    return _normalize_state(parsed)
