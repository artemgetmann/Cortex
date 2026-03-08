from __future__ import annotations

import time
from pathlib import Path

from tracks.cli_sqlite.skill_routing_cli import (
    SkillManifestEntry,
    build_skill_manifest,
    route_manifest_entries,
)


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


def test_route_manifest_entries_prefers_task_id_hint_variant() -> None:
    entries = [
        SkillManifestEntry(
            skill_ref="sqlite/incremental-reconcile",
            title="sqlite-incremental-reconcile",
            description="Stateful reconcile workflow.",
            path="/tmp/old",
            version=1,
            last_updated="2026-02-01T00:00:00+00:00",
            confidence=0.7,
        ),
        SkillManifestEntry(
            skill_ref="sqlite/incremental-reconcile-nano",
            title="sqlite-incremental-reconcile-nano",
            description="Nano-friendly reconcile workflow.",
            path="/tmp/nano",
            version=1,
            last_updated="2026-02-01T00:00:00+00:00",
            confidence=0.7,
        ),
    ]
    task_text = "SQLite task: incremental_reconcile_nano.\nGoal: reconcile rows."
    selected = route_manifest_entries(task=task_text, entries=entries, top_k=1)
    assert selected
    assert selected[0].skill_ref == "sqlite/incremental-reconcile-nano"


def test_route_manifest_entries_prefers_audit_transfer_task_hint() -> None:
    entries = [
        SkillManifestEntry(
            skill_ref="sqlite/import-aggregate",
            title="sqlite-import-aggregate",
            description="Import and aggregate rows.",
            path="/tmp/generic",
            version=1,
            last_updated="2026-02-01T00:00:00+00:00",
            confidence=0.7,
        ),
        SkillManifestEntry(
            skill_ref="sqlite/incremental-reconcile-audit-transfer",
            title="sqlite-incremental-reconcile-audit-transfer",
            description="Dedupe, reject invalid rows, and write batch audit.",
            path="/tmp/audit",
            version=1,
            last_updated="2026-02-01T00:00:00+00:00",
            confidence=0.7,
        ),
    ]
    task_text = "SQLite task: incremental_reconcile_audit_transfer.\nGoal: reconcile rows with batch audit."
    selected = route_manifest_entries(task=task_text, entries=entries, top_k=1)
    assert selected
    assert selected[0].skill_ref == "sqlite/incremental-reconcile-audit-transfer"


def test_route_manifest_entries_prefers_partial_failure_recovery_strict_hint() -> None:
    entries = [
        SkillManifestEntry(
            skill_ref="sqlite/partial-failure-recovery",
            title="sqlite-partial-failure-recovery",
            description="Handle bad rows by routing them to error_log.",
            path="/tmp/base",
            version=1,
            last_updated="2026-02-01T00:00:00+00:00",
            confidence=0.7,
        ),
        SkillManifestEntry(
            skill_ref="sqlite/partial-failure-recovery-strict",
            title="sqlite-partial-failure-recovery-strict",
            description="Validate numeric rows and use exact invalid_amount reason.",
            path="/tmp/strict",
            version=1,
            last_updated="2026-02-01T00:00:00+00:00",
            confidence=0.7,
        ),
    ]
    task_text = "SQLite task: partial_failure_recovery_strict.\nGoal: recover strict invalid amount rows."
    selected = route_manifest_entries(task=task_text, entries=entries, top_k=1)
    assert selected
    assert selected[0].skill_ref == "sqlite/partial-failure-recovery-strict"


def test_route_manifest_entries_prefers_replay_safe_task_hint() -> None:
    entries = [
        SkillManifestEntry(
            skill_ref="sqlite/incremental-reconcile",
            title="sqlite-incremental-reconcile",
            description="Stateful reconcile workflow.",
            path="/tmp/base",
            version=1,
            last_updated="2026-02-01T00:00:00+00:00",
            confidence=0.7,
        ),
        SkillManifestEntry(
            skill_ref="sqlite/incremental-reconcile-replay-safe",
            title="sqlite-incremental-reconcile-replay-safe",
            description="Replay-safe reconcile workflow with two-pass audit logging.",
            path="/tmp/replay-safe",
            version=1,
            last_updated="2026-02-01T00:00:00+00:00",
            confidence=0.7,
        ),
    ]
    task_text = "SQLite task: incremental_reconcile_replay_safe.\nGoal: replay-safe reconcile import."
    selected = route_manifest_entries(task=task_text, entries=entries, top_k=1)
    assert selected
    assert selected[0].skill_ref == "sqlite/incremental-reconcile-replay-safe"
