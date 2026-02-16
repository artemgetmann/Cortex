from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tracks.cli_sqlite import agent_cli
from tracks.cli_sqlite.domain_adapter import DomainWorkspace, ToolResult
from tracks.cli_sqlite.judge_llm import JudgeResult
from tracks.cli_sqlite.learning_cli import LessonGenerationResult
from tracks.cli_sqlite.memory_cli import read_events
from tracks.cli_sqlite.scripts import memory_timeline_demo
from tracks.cli_sqlite.scripts import run_cli_agent as run_cli_agent_script
from tracks.cli_sqlite.scripts import run_memory_stability
from tracks.cli_sqlite.skill_routing_cli import SkillManifestEntry


class _FakeUsage:
    def model_dump(self) -> dict[str, Any]:
        return {}


class _FakeBlock:
    def model_dump(self) -> dict[str, Any]:
        return {"type": "text", "text": "done"}


class _FakeResponse:
    def __init__(self) -> None:
        self.usage = _FakeUsage()
        self.content = [_FakeBlock()]


class _FakeMessages:
    def create(self, **_: Any) -> _FakeResponse:
        return _FakeResponse()


class _FakeAnthropicClient:
    def __init__(self, **_: Any) -> None:
        self.messages = _FakeMessages()


class _FakeAdapter:
    @property
    def name(self) -> str:
        return "sqlite"

    @property
    def executor_tool_name(self) -> str:
        return "run_sqlite"

    def tool_defs(self, fixture_refs: list[str], *, opaque: bool) -> list[dict[str, Any]]:
        return []

    def execute(self, tool_name: str, tool_input: dict[str, Any], workspace: DomainWorkspace) -> ToolResult:
        return ToolResult(error="not_implemented")

    def prepare_workspace(self, task_dir: Path, work_dir: Path) -> DomainWorkspace:
        return DomainWorkspace(
            task_id=task_dir.name,
            task_dir=task_dir,
            work_dir=work_dir,
            fixture_paths={},
        )

    def capture_final_state(self, workspace: DomainWorkspace) -> str:
        return ""

    def system_prompt_fragment(self) -> str:
        return "Test adapter.\n"

    def quality_keywords(self) -> re.Pattern[str]:
        return re.compile(r".")

    def build_alias_map(self, *, opaque: bool) -> dict[str, str]:
        return {}

    def docs_manifest(self) -> list[Any]:
        return []


def _configure_agent_cli_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    track_root = tmp_path / "track"
    tasks_root = track_root / "tasks"
    learning_root = track_root / "learning"
    sessions_root = track_root / "sessions"
    task_dir = tasks_root / "demo_task"
    task_dir.mkdir(parents=True, exist_ok=True)
    task_dir.joinpath("task.md").write_text("demo task", encoding="utf-8")

    monkeypatch.setattr(agent_cli, "TRACK_ROOT", track_root)
    monkeypatch.setattr(agent_cli, "TASKS_ROOT", tasks_root)
    monkeypatch.setattr(agent_cli, "LEARNING_ROOT", learning_root)
    monkeypatch.setattr(agent_cli, "SESSIONS_ROOT", sessions_root)
    monkeypatch.setattr(agent_cli, "LESSONS_PATH", learning_root / "lessons.jsonl")
    monkeypatch.setattr(agent_cli, "LESSONS_V2_PATH", learning_root / "lessons_v2.jsonl")
    monkeypatch.setattr(agent_cli, "MEMORY_EVENTS_PATH", learning_root / "memory_events.jsonl")
    monkeypatch.setattr(agent_cli, "QUEUE_PATH", learning_root / "pending_skill_patches.json")
    monkeypatch.setattr(agent_cli, "PROMOTED_PATH", learning_root / "promoted_skill_patches.json")
    monkeypatch.setattr(agent_cli, "ESCALATION_STATE_PATH", learning_root / "critic_escalation_state.json")

    monkeypatch.setattr(agent_cli.anthropic, "Anthropic", _FakeAnthropicClient)
    monkeypatch.setattr(agent_cli, "_resolve_adapter_with_mode", lambda *args, **kwargs: _FakeAdapter())

    fake_entry = SkillManifestEntry(
        skill_ref="sqlite/demo",
        title="Demo",
        description="Demo skill",
        path=str(track_root / "skills" / "sqlite" / "demo" / "SKILL.md"),
        version=1,
        last_updated="2026-02-16T00:00:00+00:00",
        confidence=0.7,
    )
    monkeypatch.setattr(agent_cli, "build_skill_manifest", lambda **kwargs: [fake_entry])

    monkeypatch.setattr(agent_cli, "llm_judge", lambda **kwargs: JudgeResult(passed=True, score=1.0, reasons=["ok"], raw_response="{}"))
    monkeypatch.setattr(agent_cli, "generate_lessons", lambda **kwargs: LessonGenerationResult(raw_lessons=[], filtered_lessons=[]))
    monkeypatch.setattr(agent_cli, "store_lessons", lambda **kwargs: 0)
    monkeypatch.setattr(agent_cli, "prune_lessons", lambda *args, **kwargs: None)
    monkeypatch.setattr(agent_cli, "upsert_lesson_records", lambda *args, **kwargs: {"inserted": 0, "merged": 0, "conflict_links": 0})
    monkeypatch.setattr(agent_cli, "apply_outcomes", lambda *args, **kwargs: {"promoted": 0, "suppressed": 0, "updated": 0})
    monkeypatch.setattr(agent_cli, "propose_skill_updates", lambda **kwargs: ([], 0.0, "[]"))
    monkeypatch.setattr(agent_cli, "parse_reflection_response", lambda raw: ([], 0.0))
    monkeypatch.setattr(agent_cli, "queue_skill_update_candidates", lambda **kwargs: {"attempted": False, "queued": 0})
    monkeypatch.setattr(agent_cli, "auto_promote_queued_candidates", lambda **kwargs: {"applied": 0, "reason": "no_updates"})
    return sessions_root


def test_memory_v2_demo_mode_suppresses_legacy_hook_events(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sessions_root = _configure_agent_cli_env(monkeypatch, tmp_path)
    cfg = SimpleNamespace(anthropic_api_key="test-key")

    demo_result = agent_cli.run_cli_agent(
        cfg=cfg,
        task_id="demo_task",
        task=None,
        session_id=101,
        max_steps=1,
        domain="sqlite",
        learning_mode="legacy",
        architecture_mode="full",
        posttask_mode="candidate",
        posttask_learn=True,
        memory_v2_demo_mode=True,
        require_skill_read=False,
    )
    demo_events = read_events(sessions_root / "session-101" / "events.jsonl")
    demo_tools = [str(row.get("tool", "")) for row in demo_events]
    assert "posttask_hook" not in demo_tools
    assert "promotion_gate" not in demo_tools
    assert demo_result.metrics["posttask_patch_attempted"] is False
    assert demo_result.metrics["posttask_skill_patching_skip_reason"] == "memory_v2_demo_mode"

    normal_result = agent_cli.run_cli_agent(
        cfg=cfg,
        task_id="demo_task",
        task=None,
        session_id=102,
        max_steps=1,
        domain="sqlite",
        learning_mode="legacy",
        architecture_mode="full",
        posttask_mode="candidate",
        posttask_learn=True,
        memory_v2_demo_mode=False,
        require_skill_read=False,
    )
    normal_events = read_events(sessions_root / "session-102" / "events.jsonl")
    normal_tools = [str(row.get("tool", "")) for row in normal_events]
    assert "posttask_hook" in normal_tools
    assert "promotion_gate" in normal_tools
    assert normal_result.metrics["posttask_patch_attempted"] is True


def test_run_cli_agent_script_forwards_demo_mode_flag(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(run_cli_agent_script, "load_config", lambda: object())
    monkeypatch.setattr(run_cli_agent_script, "run_cli_agent", lambda **kwargs: captured.update(kwargs) or SimpleNamespace(metrics={}))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_cli_agent.py",
            "--task-id",
            "aggregate_report",
            "--session",
            "42",
            "--memory-v2-demo-mode",
        ],
    )
    rc = run_cli_agent_script.main()
    assert rc == 0
    assert captured["memory_v2_demo_mode"] is True
    capsys.readouterr()


def test_run_memory_stability_forwards_demo_mode_flag(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    calls: list[dict[str, Any]] = []

    monkeypatch.setattr(run_memory_stability, "load_config", lambda: object())
    monkeypatch.setattr(run_memory_stability, "_clear_escalation", lambda: None)
    monkeypatch.setattr(run_memory_stability, "_run_phase", lambda **kwargs: calls.append(kwargs) or [])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_memory_stability.py",
            "--grid-runs",
            "0",
            "--fluxtool-runs",
            "0",
            "--retention-runs",
            "0",
            "--memory-v2-demo-mode",
        ],
    )
    rc = run_memory_stability.main()
    assert rc == 0
    assert calls
    assert all(bool(call["memory_v2_demo_mode"]) is True for call in calls)
    capsys.readouterr()


def test_memory_timeline_labels_preloaded_vs_injected_and_scores(tmp_path: Path) -> None:
    sessions_root = tmp_path / "sessions"
    session_dir = sessions_root / "session-501"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_dir.joinpath("metrics.json").write_text(
        json.dumps(
            {
                "domain": "gridtool",
                "task_id": "aggregate_report",
                "eval_passed": False,
                "eval_score": 0.0,
                "steps": 1,
                "tool_errors": 1,
                "lesson_activations": 1,
                "v2_lessons_loaded": 2,
                "v2_prerun_lesson_ids": ["lsn_pre_1", "lsn_pre_2"],
                "v2_error_events": 1,
                "v2_lesson_activations": 1,
                "v2_retrieval_help_ratio": 1.0,
                "v2_promoted": 0,
                "v2_suppressed": 0,
            }
        ),
        encoding="utf-8",
    )
    session_dir.joinpath("events.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "step": 1,
                        "tool": "run_gridtool",
                        "tool_input": {"commands": "TALLY region total=sum(amount)"},
                        "ok": False,
                        "error": (
                            "ERROR at line 1: syntax\n\n"
                            "--- HINT from prior sessions ---\n"
                            "- Use arrow syntax"
                        ),
                        "output": "",
                        "memory_v2": {
                            "injected_lessons": [{"lesson_id": "lsn_inj_1", "rule_text": "Use arrow syntax"}],
                            "retrieval_scores": [
                                {
                                    "lesson": {"lesson_id": "lsn_inj_1"},
                                    "score": {
                                        "score": 0.91,
                                        "fingerprint_match": 1.0,
                                        "tag_overlap": 0.5,
                                        "text_similarity": 0.4,
                                        "reliability": 0.7,
                                        "recency": 0.8,
                                    },
                                }
                            ],
                        },
                    }
                )
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    session_dir.joinpath("memory_events.jsonl").write_text("", encoding="utf-8")

    rendered = memory_timeline_demo._render_session(
        sessions_root=sessions_root,
        session_id=501,
        max_hints_per_step=4,
        show_ok_steps=False,
        show_all_tools=False,
        show_tool_output=False,
        max_output_chars=1200,
        lessons_path=tmp_path / "lessons_v2.jsonl",
        show_lessons=0,
    )

    assert "memory_v2_preloaded_lessons:" in rendered
    assert "count=2" in rendered
    assert "lesson_ids=lsn_pre_1,lsn_pre_2" in rendered
    assert "memory_v2_on_error_injected_lessons:" in rendered
    assert "step 01: hints=1 lesson_ids=1" in rendered
    assert "ids=lsn_inj_1" in rendered
    assert "memory_v2_retrieval_score_breakdown:" in rendered
    assert "lesson=lsn_inj_1 total=0.910" in rendered


def test_memory_timeline_handles_missing_v2_fields(tmp_path: Path) -> None:
    sessions_root = tmp_path / "sessions"
    session_dir = sessions_root / "session-502"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_dir.joinpath("metrics.json").write_text(
        json.dumps(
            {
                "domain": "gridtool",
                "task_id": "aggregate_report",
                "eval_passed": True,
                "eval_score": 1.0,
            }
        ),
        encoding="utf-8",
    )
    session_dir.joinpath("events.jsonl").write_text(
        json.dumps(
            {
                "step": 1,
                "tool": "run_gridtool",
                "tool_input": {"commands": "SHOW"},
                "ok": True,
                "error": None,
                "output": "",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    session_dir.joinpath("memory_events.jsonl").write_text("", encoding="utf-8")

    rendered = memory_timeline_demo._render_session(
        sessions_root=sessions_root,
        session_id=502,
        max_hints_per_step=4,
        show_ok_steps=False,
        show_all_tools=False,
        show_tool_output=False,
        max_output_chars=1200,
        lessons_path=tmp_path / "lessons_v2.jsonl",
        show_lessons=0,
    )

    assert "memory_v2_preloaded_lessons:" in rendered
    assert "lesson_ids=(none)" in rendered
    assert "memory_v2_on_error_injected_lessons:" in rendered
    assert "    (none)" in rendered
    assert "memory_v2_retrieval_score_breakdown:" in rendered
    assert "    (unavailable)" in rendered
