from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class SkillManifestEntry:
    skill_ref: str
    title: str
    description: str
    path: str
    last_updated: str
    confidence: float


def _derive_skill_ref(path: Path) -> str:
    parts = list(path.parts)
    if "skills" in parts:
        parts = parts[parts.index("skills") + 1 :]
    if path.name.lower() == "skill.md":
        parts = parts[:-1]
    elif path.suffix.lower() == ".md":
        parts[-1] = path.stem
    if not parts:
        return "unknown-skill"
    return "/".join(parts)


def _extract_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}

    meta: dict[str, str] = {}
    for raw in lines[1:end]:
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip().strip('"').strip("'")
        if key in {"name", "title", "description"} and value:
            meta[key] = value
    return meta


def _extract_title_and_description(text: str) -> tuple[str, str]:
    lines = [ln.rstrip() for ln in text.splitlines()]
    meta = _extract_frontmatter(text)

    title = meta.get("title") or meta.get("name") or "Untitled Skill"
    if title == "Untitled Skill":
        for line in lines:
            s = line.strip()
            if s.startswith("#"):
                title = s.lstrip("#").strip()
                break

    desc_lines: list[str] = []
    i = 0
    while i < len(lines):
        raw = lines[i].strip()
        if raw.startswith("#"):
            i += 1
            continue
        if not raw:
            i += 1
            continue
        if raw.startswith("- ") or raw.startswith("* "):
            i += 1
            continue
        # Grab up to ~3 short lines from the first prose block.
        while i < len(lines):
            candidate = lines[i].strip()
            if not candidate:
                break
            if candidate.startswith("#"):
                break
            desc_lines.append(candidate)
            if len(desc_lines) >= 3:
                break
            i += 1
        break

    description = meta.get("description", "").strip()
    if not description:
        description = " ".join(desc_lines).strip()
    if not description:
        description = "No description provided."
    return title, description


def discover_skill_files(skills_root: Path) -> list[Path]:
    return sorted(skills_root.glob("**/SKILL.md"))


def build_skill_manifest(
    *,
    skills_root: Path = Path("skills"),
    manifest_path: Path = Path("skills/skills_manifest.json"),
    default_confidence: float = 0.7,
) -> list[SkillManifestEntry]:
    if not skills_root.exists():
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text("[]\n", encoding="utf-8")
        return []

    entries: list[SkillManifestEntry] = []
    for path in discover_skill_files(skills_root):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        title, description = _extract_title_and_description(text)
        last_updated = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
        entries.append(
            SkillManifestEntry(
                skill_ref=_derive_skill_ref(path),
                title=title,
                description=description,
                path=str(path),
                last_updated=last_updated,
                confidence=float(default_confidence),
            )
        )

    entries.sort(key=lambda e: e.skill_ref)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps([asdict(e) for e in entries], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return entries


def manifest_summaries_text(entries: list[SkillManifestEntry]) -> str:
    if not entries:
        return "No skills available."
    lines = ["Available skills (title + description only):"]
    for e in entries:
        lines.append(f"- ref: {e.skill_ref}")
        lines.append(f"  title: {e.title}")
        lines.append(f"  description: {e.description}")
    return "\n".join(lines)


def route_manifest_entries(
    *,
    task: str,
    entries: list[SkillManifestEntry],
    top_k: int = 3,
) -> list[SkillManifestEntry]:
    if not entries:
        return []
    if top_k <= 0:
        return []

    task_lower = task.lower()
    task_tokens = set(_TOKEN_RE.findall(task_lower))
    is_fl_studio_task = "fl studio" in task_lower or {"fl", "studio"}.issubset(task_tokens)
    selected: list[SkillManifestEntry] = []
    selected_refs: set[str] = set()

    # Always include FL Studio basics when the task is in FL Studio.
    if is_fl_studio_task:
        basics = next((e for e in entries if e.skill_ref == "fl-studio/basics"), None)
        if basics is not None and len(selected) < top_k:
            selected.append(basics)
            selected_refs.add(basics.skill_ref)

    scored: list[tuple[float, SkillManifestEntry]] = []
    for e in entries:
        if e.skill_ref in selected_refs:
            continue
        hay = f"{e.title} {e.description} {e.skill_ref}".lower()
        tokens = set(_TOKEN_RE.findall(hay))
        overlap = len(task_tokens & tokens) if task_tokens else 0
        # Prefer richer, recently-maintained skills when overlap ties.
        score = float(overlap) + (0.1 * float(e.confidence))
        scored.append((score, e))

    scored.sort(key=lambda pair: (-pair[0], pair[1].skill_ref))
    remaining = max(0, top_k - len(selected))
    selected.extend(entry for _, entry in scored[:remaining])

    # If all scores are zero and nothing pre-selected, keep deterministic first K by ref.
    if not selected and all(score <= 0.0 for score, _ in scored):
        return sorted(entries, key=lambda e: e.skill_ref)[:top_k]
    return selected[:top_k]


def resolve_skill_content(entries: list[SkillManifestEntry], skill_ref: str) -> tuple[str | None, str | None]:
    ref = skill_ref.strip()
    if not ref:
        return None, "Missing required field: skill_ref"

    match = next((e for e in entries if e.skill_ref == ref), None)
    if match is None:
        return None, f"Unknown skill_ref: {ref!r}"

    p = Path(match.path)
    if not p.exists():
        return None, f"Skill file missing on disk: {match.path}"

    try:
        content = p.read_text(encoding="utf-8")
    except Exception as exc:
        return None, f"Failed to read skill file: {type(exc).__name__}: {exc}"
    return content, None
