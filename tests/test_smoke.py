from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path

from agent import build_system_prompt, _inject_prompt_caching
from memory import ensure_session, write_event
from run_eval import evaluate_drum_run
from self_improve import (
    SkillUpdate,
    apply_skill_updates,
    parse_reflection_response,
    queue_skill_update_candidates,
    skill_digest,
)
from skill_routing import build_skill_manifest, manifest_summaries_text, resolve_skill_content, route_manifest_entries


class AgentPromptTests(unittest.TestCase):
    def test_build_system_prompt_with_zoom_tool(self) -> None:
        prompt = build_system_prompt(tool_api_type="computer_20251124")
        self.assertIn("Use the zoom action", prompt)
        self.assertNotIn("Zoom action is unavailable", prompt)

    def test_build_system_prompt_without_zoom_tool(self) -> None:
        prompt = build_system_prompt(tool_api_type="computer_20250124")
        self.assertIn("Zoom action is unavailable", prompt)
        self.assertNotIn("Use the zoom action", prompt)

    def test_inject_prompt_caching_marks_recent_user_turns(self) -> None:
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "u1"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "a1"}]},
            {"role": "user", "content": [{"type": "text", "text": "u2"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "a2"}]},
            {"role": "user", "content": [{"type": "text", "text": "u3"}]},
        ]

        _inject_prompt_caching(messages, breakpoints=2)

        self.assertEqual(
            messages[4]["content"][-1]["cache_control"],
            {"type": "ephemeral"},
        )
        self.assertEqual(
            messages[2]["content"][-1]["cache_control"],
            {"type": "ephemeral"},
        )
        self.assertNotIn("cache_control", messages[0]["content"][-1])


class MemoryTests(unittest.TestCase):
    def test_ensure_session_and_write_event(self) -> None:
        cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                paths = ensure_session(7)
                self.assertEqual(paths.session_dir, Path("sessions/session-007"))
                self.assertTrue(paths.session_dir.exists())

                write_event(paths.jsonl_path, {"step": 1, "ok": True})
                lines = paths.jsonl_path.read_text(encoding="utf-8").strip().splitlines()
                self.assertEqual(len(lines), 1)
                self.assertIn('"step": 1', lines[0])
                self.assertIn('"ts":', lines[0])
            finally:
                os.chdir(cwd)


class SkillRoutingTests(unittest.TestCase):
    def test_build_manifest_from_skill_md_frontmatter(self) -> None:
        cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                skills_root = Path("skills")
                skill_path = skills_root / "fl-studio" / "drum-pattern" / "SKILL.md"
                skill_path.parent.mkdir(parents=True, exist_ok=True)
                skill_path.write_text(
                    (
                        "---\n"
                        "name: fl-studio-drum-pattern\n"
                        "description: Place kick hits on 1, 5, 9, 13 in Channel Rack.\n"
                        "version: 3\n"
                        "---\n\n"
                        "# Drum Pattern\n\nUse F6 first."
                    ),
                    encoding="utf-8",
                )
                manifest = build_skill_manifest(
                    skills_root=skills_root,
                    manifest_path=skills_root / "skills_manifest.json",
                )
                self.assertEqual(len(manifest), 1)
                self.assertEqual(manifest[0].skill_ref, "fl-studio/drum-pattern")
                self.assertEqual(manifest[0].title, "fl-studio-drum-pattern")
                self.assertIn("Place kick hits", manifest[0].description)
                self.assertEqual(manifest[0].version, 3)
            finally:
                os.chdir(cwd)

    def test_manifest_summaries_text_and_resolve(self) -> None:
        cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                skills_root = Path("skills")
                skill_path = skills_root / "fl-studio" / "drum-pattern" / "SKILL.md"
                skill_path.parent.mkdir(parents=True, exist_ok=True)
                skill_path.write_text(
                    "# Skill: Drum Pattern\n\nUse Channel Rack.\nClick 1,5,9,13.",
                    encoding="utf-8",
                )
                manifest = build_skill_manifest(
                    skills_root=skills_root,
                    manifest_path=skills_root / "skills_manifest.json",
                )
                summary = manifest_summaries_text(manifest)
                self.assertIn("Available skills", summary)
                self.assertIn("fl-studio/drum-pattern", summary)
                content, err = resolve_skill_content(manifest, "fl-studio/drum-pattern")
                self.assertIsNone(err)
                assert content is not None
                self.assertIn("Skill: Drum Pattern", content)
                _, err_missing = resolve_skill_content(manifest, "fl-studio/missing")
                self.assertIsNotNone(err_missing)
            finally:
                os.chdir(cwd)

    def test_route_manifest_entries_prefers_overlap(self) -> None:
        cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                skills_root = Path("skills")
                p1 = skills_root / "fl-studio" / "drum-pattern" / "SKILL.md"
                p2 = skills_root / "fl-studio" / "mixing" / "SKILL.md"
                p1.parent.mkdir(parents=True, exist_ok=True)
                p2.parent.mkdir(parents=True, exist_ok=True)
                p1.write_text("# Skill: Drum Pattern\n\nCreate four-on-the-floor kick pattern.", encoding="utf-8")
                p2.write_text("# Skill: Mixer\n\nAdjust master volume fader.", encoding="utf-8")
                manifest = build_skill_manifest(
                    skills_root=skills_root,
                    manifest_path=skills_root / "skills_manifest.json",
                )
                routed = route_manifest_entries(task="create kick drum pattern", entries=manifest, top_k=1)
                self.assertEqual(len(routed), 1)
                self.assertEqual(routed[0].skill_ref, "fl-studio/drum-pattern")
            finally:
                os.chdir(cwd)

    def test_route_manifest_entries_includes_fl_studio_basics(self) -> None:
        cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                skills_root = Path("skills")
                p_basics = skills_root / "fl-studio" / "basics" / "SKILL.md"
                p_drum = skills_root / "fl-studio" / "drum-pattern" / "SKILL.md"
                p_basics.parent.mkdir(parents=True, exist_ok=True)
                p_drum.parent.mkdir(parents=True, exist_ok=True)
                p_basics.write_text(
                    (
                        "---\n"
                        "name: fl-studio-basics\n"
                        "description: Use when any task is executed in FL Studio.\n"
                        "---\n"
                    ),
                    encoding="utf-8",
                )
                p_drum.write_text(
                    (
                        "---\n"
                        "name: fl-studio-drum-pattern\n"
                        "description: Use when creating a drum pattern in FL Studio.\n"
                        "---\n"
                    ),
                    encoding="utf-8",
                )
                manifest = build_skill_manifest(
                    skills_root=skills_root,
                    manifest_path=skills_root / "skills_manifest.json",
                )
                routed = route_manifest_entries(task="Create kick pattern in FL Studio", entries=manifest, top_k=2)
                routed_refs = [e.skill_ref for e in routed]
                self.assertIn("fl-studio/basics", routed_refs)
            finally:
                os.chdir(cwd)


class SelfImproveTests(unittest.TestCase):
    def test_parse_reflection_response(self) -> None:
        raw = """
        {
          "confidence": 0.84,
          "skill_updates": [
            {
              "skill_ref":"fl-studio/basics",
              "skill_digest":"abc123",
              "root_cause":"Repeated non-productive zoom actions delayed decisive clicks.",
              "evidence_steps":[6,7,8],
              "replace_rules":[{"find":"Use at most one zoom on the menu list if needed.","replace":"Use at most one zoom before deciding and clicking the target."}],
              "append_bullets":["After two zoom checks, click or use a key action immediately."]
            }
          ]
        }
        """
        updates, confidence = parse_reflection_response(raw)
        self.assertAlmostEqual(confidence, 0.84, places=2)
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0].skill_ref, "fl-studio/basics")
        self.assertEqual(updates[0].skill_digest, "abc123")
        self.assertEqual(updates[0].evidence_steps, [6, 7, 8])
        self.assertEqual(len(updates[0].replace_rules), 1)

    def test_apply_skill_updates_appends_learned_updates(self) -> None:
        cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                skills_root = Path("skills")
                skill_path = skills_root / "fl-studio" / "basics" / "SKILL.md"
                skill_path.parent.mkdir(parents=True, exist_ok=True)
                skill_path.write_text(
                    (
                        "---\n"
                        "name: fl-studio-basics\n"
                        "description: Use when task is in FL Studio.\n"
                        "version: 1\n"
                        "---\n\n"
                        "# FL Studio Basics\n"
                    ),
                    encoding="utf-8",
                )
                manifest = build_skill_manifest(
                    skills_root=skills_root,
                    manifest_path=skills_root / "skills_manifest.json",
                )
                updates = [
                    SkillUpdate(
                        skill_ref="fl-studio/basics",
                        skill_digest="",
                        root_cause="Agent overused inspection actions before clicking.",
                        evidence_steps=[5, 6],
                        replace_rules=[],
                        append_bullets=["Prefer decisive clicks after two inspections."],
                    )
                ]
                digest = skill_digest(skill_path.read_text(encoding="utf-8"))
                updates[0] = SkillUpdate(
                    skill_ref=updates[0].skill_ref,
                    skill_digest=digest,
                    root_cause=updates[0].root_cause,
                    evidence_steps=updates[0].evidence_steps,
                    replace_rules=updates[0].replace_rules,
                    append_bullets=updates[0].append_bullets,
                )
                result = apply_skill_updates(
                    entries=manifest,
                    updates=updates,
                    confidence=0.9,
                    min_confidence=0.7,
                    valid_steps={5, 6, 7},
                    required_skill_digests={"fl-studio/basics": digest},
                    allowed_skill_refs={"fl-studio/basics"},
                )
                self.assertEqual(result["applied"], 1)
                body = skill_path.read_text(encoding="utf-8")
                self.assertIn("## Learned Updates", body)
                self.assertIn("Prefer decisive clicks", body)
                self.assertIn("version: 2", body)
            finally:
                os.chdir(cwd)

    def test_apply_skill_updates_requires_read_before_write(self) -> None:
        cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                skills_root = Path("skills")
                skill_path = skills_root / "fl-studio" / "basics" / "SKILL.md"
                skill_path.parent.mkdir(parents=True, exist_ok=True)
                skill_path.write_text(
                    (
                        "---\n"
                        "name: fl-studio-basics\n"
                        "description: Use when task is in FL Studio.\n"
                        "version: 1\n"
                        "---\n\n"
                        "# FL Studio Basics\n"
                    ),
                    encoding="utf-8",
                )
                manifest = build_skill_manifest(
                    skills_root=skills_root,
                    manifest_path=skills_root / "skills_manifest.json",
                )
                digest = skill_digest(skill_path.read_text(encoding="utf-8"))
                updates = [
                    SkillUpdate(
                        skill_ref="fl-studio/basics",
                        skill_digest=digest,
                        root_cause="Missed decisive click after repeated zoom checks.",
                        evidence_steps=[2, 3],
                        replace_rules=[],
                        append_bullets=["After two zoom checks, click immediately."],
                    )
                ]
                result = apply_skill_updates(
                    entries=manifest,
                    updates=updates,
                    confidence=0.9,
                    min_confidence=0.7,
                    valid_steps={2, 3},
                    required_skill_digests={"fl-studio/basics": digest},
                    allowed_skill_refs=set(),
                )
                self.assertEqual(result["applied"], 0)
                body = skill_path.read_text(encoding="utf-8")
                self.assertNotIn("Learned Updates", body)
            finally:
                os.chdir(cwd)

    def test_queue_skill_update_candidates_applies_digest_and_read_gates(self) -> None:
        cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                upd = SkillUpdate(
                    skill_ref="fl-studio/basics",
                    skill_digest="deadbeef",
                    root_cause="Selector strip misclick on step row.",
                    evidence_steps=[5, 8],
                    replace_rules=[],
                    append_bullets=["Avoid selector strip; click inside step band only."],
                )
                qpath = Path("learning/pending_skill_patches.json")
                result = queue_skill_update_candidates(
                    updates=[upd],
                    confidence=0.9,
                    session_id=9901,
                    required_skill_digests={"fl-studio/basics": "deadbeef"},
                    allowed_skill_refs={"fl-studio/basics"},
                    evaluation={"passed": False},
                    queue_path=qpath,
                )
                self.assertEqual(result["queued"], 1)
                data = json.loads(qpath.read_text(encoding="utf-8"))
                self.assertEqual(len(data), 1)
                self.assertEqual(data[0]["updates"][0]["skill_ref"], "fl-studio/basics")
            finally:
                os.chdir(cwd)


class RunEvalTests(unittest.TestCase):
    def test_evaluate_drum_run_flags_selector_misclick(self) -> None:
        task = "Create a 4-on-the-floor kick drum pattern in FL Studio"
        events = [
            {"step": 3, "tool": "computer", "tool_input": {"action": "zoom"}},
            {"step": 4, "tool": "computer", "tool_input": {"action": "zoom"}},
            {"step": 5, "tool": "computer", "tool_input": {"action": "left_click", "coordinate": [411, 150]}},
            {"step": 8, "tool": "computer", "tool_input": {"action": "left_click", "coordinate": [422, 150]}},
            {"step": 10, "tool": "computer", "tool_input": {"action": "left_click", "coordinate": [492, 150]}},
            {"step": 12, "tool": "computer", "tool_input": {"action": "left_click", "coordinate": [563, 150]}},
        ]
        evaluation = evaluate_drum_run(task, events).to_dict()
        self.assertTrue(evaluation["applicable"])
        self.assertFalse(evaluation["passed"])
        self.assertIn("selector_zone_misclick", evaluation["reasons"])


if __name__ == "__main__":
    unittest.main()
