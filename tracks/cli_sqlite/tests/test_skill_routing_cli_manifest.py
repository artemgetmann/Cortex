from __future__ import annotations

import time
from pathlib import Path

from tracks.cli_sqlite.skill_routing_cli import build_skill_manifest


def test_build_skill_manifest_skips_noop_rewrite(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "demo" / "basics"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        (
            "---\n"
            "title: Demo Skill\n"
            "description: Demo skill description.\n"
            "version: 1\n"
            "---\n"
            "\n"
            "# Demo Skill\n"
            "Use this skill for deterministic manifest tests.\n"
        ),
        encoding="utf-8",
    )
    manifest_path = skills_root / "skills_manifest.json"

    build_skill_manifest(skills_root=skills_root, manifest_path=manifest_path)
    first_mtime = manifest_path.stat().st_mtime_ns
    first_payload = manifest_path.read_text(encoding="utf-8")

    # Ensure mtime granularity does not mask an unintended rewrite.
    time.sleep(0.02)
    build_skill_manifest(skills_root=skills_root, manifest_path=manifest_path)
    second_mtime = manifest_path.stat().st_mtime_ns
    second_payload = manifest_path.read_text(encoding="utf-8")

    assert first_payload == second_payload
    assert second_mtime == first_mtime
