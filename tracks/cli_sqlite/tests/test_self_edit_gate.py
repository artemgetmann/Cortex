from __future__ import annotations

import sys
from pathlib import Path

from tracks.cli_sqlite.self_edit_gate import apply_guarded_self_edit_updates, build_self_edit_manifest_entries
from tracks.cli_sqlite.self_improve_cli import ReplaceRule, SkillUpdate, skill_digest
from tracks.cli_sqlite.skill_routing_cli import SkillManifestEntry


def _entry_for(path: Path, *, skill_ref: str) -> SkillManifestEntry:
    return SkillManifestEntry(
        skill_ref=skill_ref,
        title="test",
        description="test",
        path=str(path),
        version=1,
        last_updated="2026-02-25T00:00:00+00:00",
        confidence=0.7,
    )


def test_apply_guarded_self_edit_updates_accepts_when_checks_pass(tmp_path: Path) -> None:
    target = tmp_path / "target.py"
    target.write_text("value = 1\n", encoding="utf-8")
    entry = _entry_for(target, skill_ref="orchestration/agent_cli")
    update = SkillUpdate(
        skill_ref=entry.skill_ref,
        skill_digest=skill_digest(target.read_text(encoding="utf-8")),
        root_cause="test",
        evidence_steps=[2],
        replace_rules=[ReplaceRule(find="value = 1", replace="value = 2")],
        append_bullets=[],
    )
    result = apply_guarded_self_edit_updates(
        entries=[entry],
        updates=[update],
        confidence=0.9,
        track_root=tmp_path,
        required_skill_digests={entry.skill_ref: update.skill_digest},
        allowed_skill_refs={entry.skill_ref},
        check_commands=[[sys.executable, "-c", "print('ok')"]],
    )
    assert result["applied"] == 1
    assert result["rolled_back"] is False
    assert "value = 2" in target.read_text(encoding="utf-8")


def test_apply_guarded_self_edit_updates_rolls_back_on_failed_checks(tmp_path: Path) -> None:
    target = tmp_path / "target.py"
    target.write_text("value = 1\n", encoding="utf-8")
    entry = _entry_for(target, skill_ref="orchestration/agent_cli")
    update = SkillUpdate(
        skill_ref=entry.skill_ref,
        skill_digest=skill_digest(target.read_text(encoding="utf-8")),
        root_cause="test",
        evidence_steps=[2],
        replace_rules=[ReplaceRule(find="value = 1", replace="value = 3")],
        append_bullets=[],
    )
    result = apply_guarded_self_edit_updates(
        entries=[entry],
        updates=[update],
        confidence=0.9,
        track_root=tmp_path,
        required_skill_digests={entry.skill_ref: update.skill_digest},
        allowed_skill_refs={entry.skill_ref},
        check_commands=[[sys.executable, "-c", "import sys; sys.exit(1)"]],
    )
    assert result["applied"] == 0
    assert result["rolled_back"] is True
    assert result["skipped_reason"] == "verification_failed"
    assert target.read_text(encoding="utf-8") == "value = 1\n"


def test_apply_guarded_self_edit_updates_rejects_disallowed_refs(tmp_path: Path) -> None:
    target = tmp_path / "target.py"
    target.write_text("value = 1\n", encoding="utf-8")
    entry = _entry_for(target, skill_ref="orchestration/agent_cli")
    update = SkillUpdate(
        skill_ref=entry.skill_ref,
        skill_digest=skill_digest(target.read_text(encoding="utf-8")),
        root_cause="test",
        evidence_steps=[2],
        replace_rules=[ReplaceRule(find="value = 1", replace="value = 4")],
        append_bullets=[],
    )
    result = apply_guarded_self_edit_updates(
        entries=[entry],
        updates=[update],
        confidence=0.9,
        track_root=tmp_path,
        required_skill_digests={entry.skill_ref: update.skill_digest},
        allowed_skill_refs={"orchestration/run_observability"},
        check_commands=[[sys.executable, "-c", "print('ok')"]],
    )
    assert result["applied"] == 0
    assert result["skipped_reason"] == "no_applicable_changes"
    assert int(result["rejection_counts"]["disallowed_ref"]) >= 1


def test_build_self_edit_manifest_entries_resolves_from_track_root(tmp_path: Path) -> None:
    (tmp_path / "agent_cli.py").write_text("pass\n", encoding="utf-8")
    scripts = tmp_path / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "run_cli_agent.py").write_text("pass\n", encoding="utf-8")
    (scripts / "run_learning_curve.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "run_observability.py").write_text("pass\n", encoding="utf-8")

    entries = build_self_edit_manifest_entries(track_root=tmp_path)
    refs = {entry.skill_ref for entry in entries}
    assert "orchestration/agent_cli" in refs
    assert "orchestration/run_cli_agent_script" in refs
    assert "orchestration/run_observability" in refs
    assert "orchestration/run_learning_curve_script" in refs
