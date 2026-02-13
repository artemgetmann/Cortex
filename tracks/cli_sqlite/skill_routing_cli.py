from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class SkillManifestEntry:
    skill_ref: str
    title: str
    description: str
    path: str
    version: int
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
    return "/".join(parts) if parts else "unknown-skill"


def _extract_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end is None:
        return {}
    meta: dict[str, str] = {}
    for raw in lines[1:end]:
        line = raw.strip()
        if not line or ":" not in line or line.startswith("#"):
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip().strip('"').strip("'")
        if key in {"name", "title", "description", "version"} and value:
            meta[key] = value
    return meta


def _extract_title_and_description(text: str) -> tuple[str, str]:
    lines = [line.rstrip() for line in text.splitlines()]
    meta = _extract_frontmatter(text)
    title = meta.get("title") or meta.get("name") or "Untitled Skill"
    if title == "Untitled Skill":
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                title = stripped.lstrip("#").strip()
                break

    description = meta.get("description", "").strip()
    if description:
        return title, description

    prose: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("- ") or stripped.startswith("* "):
            continue
        prose.append(stripped)
        if len(prose) >= 3:
            break
    return title, (" ".join(prose).strip() or "No description provided.")


def _extract_version(text: str) -> int:
    meta = _extract_frontmatter(text)
    raw = str(meta.get("version", "1")).strip()
    if raw.isdigit():
        return max(1, int(raw))
    return 1


def discover_skill_files(skills_root: Path) -> list[Path]:
    return sorted(skills_root.glob("**/SKILL.md"))


def build_skill_manifest(
    *,
    skills_root: Path,
    manifest_path: Path,
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
        version = _extract_version(text)
        entries.append(
            SkillManifestEntry(
                skill_ref=_derive_skill_ref(path),
                title=title,
                description=description,
                path=str(path),
                version=version,
                last_updated=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
                confidence=float(default_confidence),
            )
        )

    entries.sort(key=lambda item: item.skill_ref)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps([asdict(entry) for entry in entries], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return entries


def manifest_summaries_text(entries: list[SkillManifestEntry]) -> str:
    if not entries:
        return "No skills available."
    lines = ["Available skills (summary metadata only):"]
    for entry in entries:
        lines.append(f"- ref: {entry.skill_ref}")
        lines.append(f"  title: {entry.title}")
        lines.append(f"  description: {entry.description}")
    return "\n".join(lines)


def route_manifest_entries(*, task: str, entries: list[SkillManifestEntry], top_k: int = 2) -> list[SkillManifestEntry]:
    if not entries or top_k <= 0:
        return []

    task_tokens = set(TOKEN_RE.findall(task.lower()))
    scored: list[tuple[float, SkillManifestEntry]] = []
    for entry in entries:
        haystack = f"{entry.title} {entry.description} {entry.skill_ref}".lower()
        overlap = len(task_tokens & set(TOKEN_RE.findall(haystack)))
        score = float(overlap) + (0.1 * float(entry.confidence))
        scored.append((score, entry))

    scored.sort(key=lambda row: (-row[0], row[1].skill_ref))
    selected = [entry for _, entry in scored[:top_k]]
    if selected:
        return selected
    return sorted(entries, key=lambda entry: entry.skill_ref)[:top_k]


def resolve_skill_content(entries: list[SkillManifestEntry], skill_ref: str) -> tuple[str | None, str | None]:
    target = skill_ref.strip()
    if not target:
        return None, "Missing required field: skill_ref"
    match = next((entry for entry in entries if entry.skill_ref == target), None)
    if match is None:
        return None, f"Unknown skill_ref: {target!r}"
    path = Path(match.path)
    if not path.exists():
        return None, f"Skill file missing on disk: {match.path}"
    try:
        return path.read_text(encoding="utf-8"), None
    except Exception as exc:
        return None, f"Failed to read skill file: {type(exc).__name__}: {exc}"
