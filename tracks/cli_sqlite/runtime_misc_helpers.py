from __future__ import annotations

import base64
import hashlib
from typing import Any


def _is_dependency_or_setup_failure(
    *,
    error_text: str,
    error_tags: list[str],
    dependency_setup_tags: set[str],
    dependency_setup_patterns: list[Any],
) -> bool:
    tags = {str(tag).strip().lower() for tag in error_tags if str(tag).strip()}
    if tags & dependency_setup_tags:
        return True
    lowered = str(error_text or "").strip().lower()
    return any(pattern.search(lowered) for pattern in dependency_setup_patterns)


def _hash_base64_png(image_b64: str | None) -> str | None:
    if not isinstance(image_b64, str):
        return None
    try:
        data = base64.b64decode(image_b64.encode("ascii"), validate=True)
    except Exception:
        return None
    digest = hashlib.sha256(data).hexdigest()
    return f"sha256:{digest}"


def _normalize_coordinate(coord: Any) -> tuple[int, int] | None:
    if not (isinstance(coord, (list, tuple)) and len(coord) == 2):
        return None
    try:
        x = int(coord[0])
        y = int(coord[1])
    except (TypeError, ValueError):
        return None
    return x, y


def _normalize_region(region: Any) -> tuple[int, int, int, int] | None:
    if not (isinstance(region, (list, tuple)) and len(region) == 4):
        return None
    try:
        coords = tuple(int(value) for value in region)
    except (TypeError, ValueError):
        return None
    return coords


def _extract_computer_use_metadata(
    tool_input: Any,
    result: Any,
    *,
    normalize_coordinate_func,
    normalize_region_func,
    hash_base64_png_func,
) -> dict[str, Any]:
    if not isinstance(tool_input, dict):
        return {}
    metadata: dict[str, Any] = {}

    action = tool_input.get("action")
    if isinstance(action, str) and action.strip():
        metadata["action"] = action.strip()

    coordinate = normalize_coordinate_func(tool_input.get("coordinate"))
    if coordinate:
        metadata["coordinate"] = [coordinate[0], coordinate[1]]

    start = normalize_coordinate_func(tool_input.get("start_coordinate"))
    if start:
        metadata["start_coordinate"] = [start[0], start[1]]
    end = normalize_coordinate_func(tool_input.get("coordinate"))
    if end and start:
        metadata["end_coordinate"] = [end[0], end[1]]

    region = normalize_region_func(tool_input.get("region"))
    if region:
        metadata["region"] = [region[0], region[1], region[2], region[3]]
        if metadata.get("action") == "zoom":
            metadata["zoom_region"] = metadata["region"]

    screenshot_hash = hash_base64_png_func(getattr(result, "base64_image_png", None))
    if screenshot_hash:
        metadata["screenshot_hash"] = screenshot_hash

    modifiers = tool_input.get("modifiers")
    if isinstance(modifiers, (list, tuple)) and modifiers:
        metadata["modifiers"] = [str(mod).strip() for mod in modifiers if str(mod).strip()]

    return metadata


def _build_reflection_prompt(
    *,
    error_text: str,
    fingerprint: str,
    reason: str,
    include_dependency_fallback: bool = False,
) -> str:
    """
    Create a deterministic reflection request for stuck/error-heavy runs.

    The prompt explicitly requests diagnosis + smallest correction, then
    instructs the model to continue with tool use in the same turn.
    """
    reason_line = f"Trigger: {reason}." if reason else "Trigger: error escalation."
    prompt = (
        "Reflection required before the next tool call.\n"
        f"{reason_line}\n"
        f"Last error: {error_text.strip()}\n"
        f"Fingerprint: {fingerprint}\n"
        "Explain why the failure happened and the smallest corrective change. "
        "Then proceed with the next tool call."
    )
    if not include_dependency_fallback:
        return prompt
    return (
        f"{prompt}\n"
        "Deterministic fallback check:\n"
        "- Treat this fingerprint as a repeated dependency/setup failure.\n"
        "- Do not repeat the same failing setup path.\n"
        "- Choose the smallest local alternative that avoids the missing dependency."
    )
