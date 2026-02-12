from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from agent import build_system_prompt, _inject_prompt_caching
from memory import ensure_session, write_event


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


if __name__ == "__main__":
    unittest.main()
