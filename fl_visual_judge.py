from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


@dataclass(frozen=True)
class VisualJudgeResult:
    passed: bool
    score: float
    confidence: float
    reasons: list[str]
    observed_kick_label: str
    observed_active_steps: list[int]
    raw_response: str
    reference_images_used: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "observed_kick_label": self.observed_kick_label,
            "observed_active_steps": self.observed_active_steps,
            "raw_response": self.raw_response,
            "reference_images_used": self.reference_images_used,
        }


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if not text:
        return {}
    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _clamp01(value: Any, *, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if out < 0.0:
        return 0.0
    if out > 1.0:
        return 1.0
    return out


def _normalize_steps(raw_steps: Any) -> list[int]:
    if not isinstance(raw_steps, list):
        return []
    out: list[int] = []
    for item in raw_steps:
        if isinstance(item, int) and 1 <= item <= 16:
            out.append(item)
    return sorted(set(out))


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


def judge_fl_visual(
    *,
    client: Any,
    model: str,
    final_screenshot_b64: str,
    task: str,
    rubric: str,
    reference_images: Sequence[Path] = (),
) -> VisualJudgeResult:
    """
    Visual judge for FL Studio UI outcomes.

    This is intentionally separate from the executor and from extract_fl_state so
    we can cross-check outcome quality with an independent authority.
    """
    system = (
        "You are a strict visual judge for FL Studio outcomes.\n"
        "You receive one final run screenshot and zero or more reference screenshots.\n"
        "Return STRICT JSON object only (no markdown):\n"
        "{\n"
        '  "passed": true|false,\n'
        '  "score": 0.0,\n'
        '  "confidence": 0.0,\n'
        '  "reasons": ["..."],\n'
        '  "observed_kick_label": "...",\n'
        '  "observed_active_steps": [1,5,9,13]\n'
        "}\n"
        "Rules:\n"
        "- Compare final screenshot against rubric and references.\n"
        "- If uncertain, mark passed=false and lower confidence.\n"
        "- Do not fabricate unseen details.\n"
        "- Step numbering is 1..16 left-to-right.\n"
    )

    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"TASK:\n{task}\n\n"
                f"RUBRIC:\n{rubric}\n\n"
                "PRIMARY_FINAL_SCREENSHOT follows."
            ),
        },
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": final_screenshot_b64,
            },
        },
    ]
    refs_used: list[str] = []
    if reference_images:
        content.append(
            {
                "type": "text",
                "text": "REFERENCE_SCREENSHOTS follow. Treat these as success exemplars.",
            }
        )
        for ref in reference_images:
            block = _image_block_from_path(ref)
            if block is None:
                continue
            refs_used.append(str(ref))
            content.append({"type": "text", "text": f"reference_image={ref}"})
            content.append(block)

    resp = client.messages.create(
        model=model,
        max_tokens=500,
        system=system,
        messages=[{"role": "user", "content": content}],
    )
    raw = ""
    for block in resp.content:
        bd = block.model_dump() if hasattr(block, "model_dump") else block  # type: ignore[attr-defined]
        if isinstance(bd, dict) and bd.get("type") == "text":
            raw += str(bd.get("text", ""))

    parsed = _extract_json_object(raw)
    if not parsed:
        return VisualJudgeResult(
            passed=False,
            score=0.0,
            confidence=0.0,
            reasons=["visual_judge_unparseable"],
            observed_kick_label="",
            observed_active_steps=[],
            raw_response=raw[:2500],
            reference_images_used=refs_used,
        )

    reasons = parsed.get("reasons")
    if not isinstance(reasons, list):
        reasons = []
    normalized_reasons = [str(x) for x in reasons if str(x).strip()][:8]
    observed_label = str(parsed.get("observed_kick_label", "")).strip()
    observed_steps = _normalize_steps(parsed.get("observed_active_steps"))

    return VisualJudgeResult(
        passed=bool(parsed.get("passed", False)),
        score=round(_clamp01(parsed.get("score"), default=0.0), 3),
        confidence=round(_clamp01(parsed.get("confidence"), default=0.0), 3),
        reasons=normalized_reasons,
        observed_kick_label=observed_label,
        observed_active_steps=observed_steps,
        raw_response=raw[:2500],
        reference_images_used=refs_used,
    )
