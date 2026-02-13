from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skill_routing import SkillManifestEntry, build_skill_manifest


@dataclass(frozen=True)
class SkillUpdate:
    skill_ref: str
    append_bullets: list[str]


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if not text:
        return None
    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def parse_reflection_response(raw: str) -> tuple[list[SkillUpdate], float]:
    obj = _extract_json_object(raw)
    if obj is None:
        return [], 0.0

    confidence = float(obj.get("confidence", 0.0) or 0.0)
    updates_raw = obj.get("skill_updates")
    if not isinstance(updates_raw, list):
        return [], confidence

    updates: list[SkillUpdate] = []
    for item in updates_raw:
        if not isinstance(item, dict):
            continue
        skill_ref = item.get("skill_ref")
        append_bullets = item.get("append_bullets")
        if not isinstance(skill_ref, str):
            continue
        if not isinstance(append_bullets, list):
            continue
        cleaned: list[str] = []
        for bullet in append_bullets:
            if not isinstance(bullet, str):
                continue
            b = " ".join(bullet.strip().split())
            if not b:
                continue
            if len(b) > 220:
                b = b[:217] + "..."
            cleaned.append(b)
        if cleaned:
            updates.append(SkillUpdate(skill_ref=skill_ref.strip(), append_bullets=cleaned[:5]))
    return updates, confidence


def apply_skill_updates(
    *,
    entries: list[SkillManifestEntry],
    updates: list[SkillUpdate],
    confidence: float,
    min_confidence: float = 0.7,
    max_skills: int = 2,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "attempted": bool(updates),
        "applied": 0,
        "updated_skill_refs": [],
        "confidence": confidence,
        "skipped_reason": None,
    }

    if not updates:
        result["skipped_reason"] = "no_updates"
        return result
    if confidence < min_confidence:
        result["skipped_reason"] = f"low_confidence<{min_confidence}"
        return result

    by_ref = {e.skill_ref: e for e in entries}
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for upd in updates[:max_skills]:
        entry = by_ref.get(upd.skill_ref)
        if entry is None:
            continue
        p = Path(entry.path)
        if not p.exists():
            continue

        text = p.read_text(encoding="utf-8")
        section = "## Learned Updates"
        if section not in text:
            if not text.endswith("\n"):
                text += "\n"
            text += f"\n{section}\n"

        changed = False
        for bullet in upd.append_bullets:
            line = f"- [{stamp}] {bullet}"
            if line in text:
                continue
            if not text.endswith("\n"):
                text += "\n"
            text += line + "\n"
            changed = True

        if changed:
            backup = p.with_suffix(p.suffix + ".bak")
            if not backup.exists():
                backup.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
            p.write_text(text, encoding="utf-8")
            result["applied"] += 1
            result["updated_skill_refs"].append(upd.skill_ref)

    if result["applied"] == 0 and result["skipped_reason"] is None:
        result["skipped_reason"] = "no_applicable_changes"

    # Keep manifest aligned if any skill changed.
    if result["applied"] > 0:
        build_skill_manifest()

    return result
