#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


ALLOWED_FRONTMATTER_KEYS = {"name", "description", "version", "license", "allowed-tools", "metadata"}
NAME_RE = re.compile(r"^[a-z0-9-]{1,64}$")


@dataclass
class ValidationIssue:
    path: Path
    message: str


def parse_frontmatter(text: str) -> tuple[dict[str, str], str | None]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, "missing YAML frontmatter start delimiter"

    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, "missing YAML frontmatter end delimiter"

    meta: dict[str, str] = {}
    for raw in lines[1:end]:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta, None


def validate_skill_file(path: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        return [ValidationIssue(path, f"failed to read file: {type(exc).__name__}: {exc}")]

    meta, err = parse_frontmatter(text)
    if err:
        return [ValidationIssue(path, err)]

    unknown = set(meta.keys()) - ALLOWED_FRONTMATTER_KEYS
    if unknown:
        issues.append(
            ValidationIssue(
                path,
                f"unknown frontmatter keys: {sorted(unknown)} (allowed: {sorted(ALLOWED_FRONTMATTER_KEYS)})",
            )
        )

    name = meta.get("name", "").strip()
    if not name:
        issues.append(ValidationIssue(path, "missing required frontmatter key: name"))
    elif not NAME_RE.match(name) or name.startswith("-") or name.endswith("-") or "--" in name:
        issues.append(
            ValidationIssue(
                path,
                "name must be hyphen-case [a-z0-9-], 1..64 chars, no leading/trailing/consecutive hyphens",
            )
        )

    description = meta.get("description", "").strip()
    if not description:
        issues.append(ValidationIssue(path, "missing required frontmatter key: description"))
    else:
        if len(description) > 1024:
            issues.append(ValidationIssue(path, "description exceeds 1024 chars"))
        if "<" in description or ">" in description:
            issues.append(ValidationIssue(path, "description cannot contain angle brackets"))
        # Enforce trigger-oriented metadata for routing quality.
        if "use when" not in description.lower():
            issues.append(ValidationIssue(path, "description should include explicit trigger phrase: 'Use when ...'"))

    raw_version = meta.get("version", "").strip()
    if not raw_version:
        issues.append(ValidationIssue(path, "missing required frontmatter key: version"))
    else:
        try:
            version = int(raw_version)
            if version < 1:
                issues.append(ValidationIssue(path, "version must be an integer >= 1"))
        except ValueError:
            issues.append(ValidationIssue(path, "version must be an integer >= 1"))

    return issues


def main() -> int:
    skills_root = Path("skills")
    skill_files = sorted(skills_root.glob("**/SKILL.md"))
    if not skill_files:
        print("No SKILL.md files found under skills/")
        return 1

    issues: list[ValidationIssue] = []
    for p in skill_files:
        issues.extend(validate_skill_file(p))

    if issues:
        print("Skill validation failed:\n")
        for issue in issues:
            print(f"- {issue.path}: {issue.message}")
        print(f"\nTotal issues: {len(issues)}")
        return 1

    print(f"Skill validation passed: {len(skill_files)} skill files checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
