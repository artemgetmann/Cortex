from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tracks.cli_sqlite import agent_cli
from tracks.cli_sqlite.domain_adapter import DomainWorkspace, ToolResult
from tracks.cli_sqlite.judge_llm import JudgeResult
from tracks.cli_sqlite.learning_cli import LessonGenerationResult
from tracks.cli_sqlite.loop_watchdog import (
    LoopWatchdogSnapshot,
    LoopWatchdogState,
    evaluate_watchdog_policy,
    load_watchdog_state,
    next_watchdog_state,
    persist_watchdog_state,
    state_path_for_learning_root,
)
from tracks.cli_sqlite.memory_cli import read_events
from tracks.cli_sqlite.skill_routing_cli import SkillManifestEntry


class _FakeUsage:
    def model_dump(self) -> dict[str, Any]:
        return {}


class _FakeBlock:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = dict(payload)

    def model_dump(self) -> dict[str, Any]:
        return dict(self._payload)


class _FakeResponse:
    def __init__(self, blocks: list[dict[str, Any]]) -> None:
        self.usage = _FakeUsage()
        self.content = [_FakeBlock(block) for block in blocks]


class _FakeMessages:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = list(responses)
        self._idx = 0

    def create(self, **_: Any) -> _FakeResponse:
        if self._idx < len(self._responses):
            response = self._responses[self._idx]
            self._idx += 1
            return response
        return _FakeResponse([{"type": "text", "text": "done"}])


class _FakeAnthropicClient:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.messages = _FakeMessages(responses)


class _FailingAdapter:
    @property
    def name(self) -> str:
        return "sqlite"

    @property
    def executor_tool_name(self) -> str:
        return "run_sqlite"

    def tool_defs(self, fixture_refs: list[str], *, opaque: bool) -> list[dict[str, Any]]:
        del fixture_refs, opaque
        return [
            {
                "name": "run_sqlite",
                "input_schema": {
                    "type": "object",
                    "properties": {"sql": {"type": "string"}},
                    "required": ["sql"],
                    "additionalProperties": False,
                },
            }
        ]

    def execute(self, tool_name: str, tool_input: dict[str, Any], workspace: DomainWorkspace) -> ToolResult:
        del workspace
        if tool_name != "run_sqlite":
            return ToolResult(error="unknown_tool")
        if not isinstance(tool_input.get("sql"), str):
            return ToolResult(error="missing_sql")
        return ToolResult(error="simulated hard failure")

    def prepare_workspace(self, task_dir: Path, work_dir: Path) -> DomainWorkspace:
        return DomainWorkspace(
            task_id=task_dir.name,
            task_dir=task_dir,
            work_dir=work_dir,
            fixture_paths={},
        )

    def capture_final_state(self, workspace: DomainWorkspace) -> str:
        del workspace
        return ""

    def system_prompt_fragment(self) -> str:
        return "Watchdog test adapter.\n"

    def quality_keywords(self) -> re.Pattern[str]:
        return re.compile(r".")

    def build_alias_map(self, *, opaque: bool) -> dict[str, str]:
        del opaque
        return {}

    def docs_manifest(self) -> list[Any]:
        return []


def _tool_use_response(*, tool_use_id: str) -> _FakeResponse:
    return _FakeResponse(
        [
            {
                "type": "tool_use",
                "id": tool_use_id,
                "name": "run_sqlite",
                "input": {"sql": "SELECT 1;"},
            }
        ]
    )


def test_watchdog_trips_safe_mode_on_repeated_hard_failure_signal() -> None:
    state = LoopWatchdogState()
    decision = evaluate_watchdog_policy(
        state=state,
        snapshot=LoopWatchdogSnapshot(
            repeated_hard_failure_signatures=1,
            contract_gap_unresolved_count=0,
            rejection_streak=0,
        ),
    )
    assert decision.safe_mode_active is True
    assert decision.safe_mode_triggered is True
    assert decision.stop_flag is False
    assert decision.safe_mode_failure_streak == 1
    assert "repeated_hard_failure_signatures" in decision.failure_signals


def test_watchdog_sets_stop_flag_when_failures_continue_in_safe_mode() -> None:
    state = LoopWatchdogState(
        safe_mode_active=True,
        safe_mode_failure_streak=1,
        rejection_streak=0,
    )
    decision = evaluate_watchdog_policy(
        state=state,
        snapshot=LoopWatchdogSnapshot(
            repeated_hard_failure_signatures=1,
            contract_gap_unresolved_count=0,
            rejection_streak=0,
        ),
    )
    assert decision.safe_mode_active is True
    assert decision.safe_mode_triggered is False
    assert decision.stop_flag is True
    assert decision.safe_mode_failure_streak == 2


def test_watchdog_persists_state_and_tracks_rejection_streak(tmp_path: Path) -> None:
    state_path = state_path_for_learning_root(learning_root=tmp_path)
    initial = load_watchdog_state(state_path=state_path)
    assert initial.safe_mode_active is False

    neutral_decision = evaluate_watchdog_policy(
        state=initial,
        snapshot=LoopWatchdogSnapshot(),
    )
    after_one_rejection = next_watchdog_state(
        state=initial,
        decision=neutral_decision,
        run_id="run-1",
        posttask_rejection_total=1,
    )
    assert after_one_rejection.rejection_streak == 1
    assert after_one_rejection.safe_mode_active is False

    after_two_rejections = next_watchdog_state(
        state=after_one_rejection,
        decision=neutral_decision,
        run_id="run-2",
        posttask_rejection_total=1,
    )
    assert after_two_rejections.rejection_streak == 2
    assert after_two_rejections.safe_mode_active is True

    persist_watchdog_state(state_path=state_path, state=after_two_rejections)
    loaded = load_watchdog_state(state_path=state_path)
    assert loaded.rejection_streak == 2
    assert loaded.safe_mode_active is True
    assert loaded.last_run_id == "run-2"


def test_agent_cli_watchdog_disables_patching_and_sets_stop_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    track_root = tmp_path / "track"
    tasks_root = track_root / "tasks"
    learning_root = track_root / "learning"
    sessions_root = track_root / "sessions"
    task_dir = tasks_root / "watchdog_task"
    task_dir.mkdir(parents=True, exist_ok=True)
    task_dir.joinpath("task.md").write_text("watchdog integration task", encoding="utf-8")

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

    adapter = _FailingAdapter()
    monkeypatch.setattr(agent_cli, "_resolve_adapter_with_mode", lambda *args, **kwargs: adapter)

    responses = [
        _tool_use_response(tool_use_id="tool-1"),
        _tool_use_response(tool_use_id="tool-2"),
    ]
    monkeypatch.setattr(
        agent_cli.anthropic,
        "Anthropic",
        lambda **kwargs: _FakeAnthropicClient(list(responses)),
    )

    skill_file = track_root / "skills" / "sqlite" / "watchdog" / "SKILL.md"
    skill_file.parent.mkdir(parents=True, exist_ok=True)
    skill_file.write_text("# watchdog\n", encoding="utf-8")

    fake_entry = SkillManifestEntry(
        skill_ref="sqlite/watchdog",
        title="watchdog",
        description="watchdog skill",
        path=str(skill_file),
        version=1,
        last_updated="2026-02-25T00:00:00Z",
        confidence=0.8,
    )
    monkeypatch.setattr(agent_cli, "build_skill_manifest", lambda **kwargs: [fake_entry])
    monkeypatch.setattr(agent_cli, "route_manifest_entries", lambda **kwargs: [fake_entry])
    monkeypatch.setattr(agent_cli, "build_self_edit_manifest_entries", lambda **kwargs: [fake_entry])
    monkeypatch.setattr(agent_cli, "generate_lessons", lambda **kwargs: LessonGenerationResult(raw_lessons=[], filtered_lessons=[]))
    monkeypatch.setattr(agent_cli, "store_lessons", lambda **kwargs: 0)
    monkeypatch.setattr(agent_cli, "prune_lessons", lambda *args, **kwargs: None)
    monkeypatch.setattr(agent_cli, "upsert_lesson_records", lambda *args, **kwargs: {"inserted": 0, "merged": 0, "conflict_links": 0})
    monkeypatch.setattr(agent_cli, "apply_outcomes", lambda *args, **kwargs: {"promoted": 0, "suppressed": 0, "updated": 0})
    monkeypatch.setattr(agent_cli, "queue_skill_update_candidates", lambda **kwargs: {"attempted": False, "queued": 0, "rejection_counts": {}})
    monkeypatch.setattr(agent_cli, "auto_promote_queued_candidates", lambda **kwargs: {"applied": 0, "reason": "no_updates"})
    monkeypatch.setattr(
        agent_cli,
        "llm_judge",
        lambda **kwargs: JudgeResult(
            passed=False,
            score=0.0,
            reasons=["judge_failed"],
            doc_grounding=[],
            raw_response="{}",
        ),
    )
    monkeypatch.setattr(
        agent_cli,
        "propose_skill_updates",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("watchdog should disable posttask patch proposal")),
    )
    monkeypatch.setattr(
        agent_cli,
        "apply_guarded_self_edit_updates",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("watchdog should disable guarded self-edit")),
    )

    cfg = SimpleNamespace(anthropic_api_key="test-key")
    first = agent_cli.run_cli_agent(
        cfg=cfg,
        task_id="watchdog_task",
        task=None,
        session_id=701,
        max_steps=2,
        domain="sqlite",
        posttask_learn=True,
        memory_v2_demo_mode=False,
        require_skill_read=False,
        self_edit_mode=True,
        llm_backend="anthropic",
    )
    assert first.metrics["loop_watchdog_safe_mode_active"] is True
    assert first.metrics["loop_watchdog_safe_mode_triggered"] is True
    assert first.metrics["loop_watchdog_stop_flag"] is False
    assert first.metrics["posttask_patch_attempted"] is False
    assert first.metrics["posttask_skill_patching_skip_reason"] == "loop_watchdog_safe_mode"
    assert first.metrics["self_edit_mode_effective"] is False
    assert first.metrics["loop_watchdog_state_persisted"] is True

    second = agent_cli.run_cli_agent(
        cfg=cfg,
        task_id="watchdog_task",
        task=None,
        session_id=702,
        max_steps=2,
        domain="sqlite",
        posttask_learn=True,
        memory_v2_demo_mode=False,
        require_skill_read=False,
        self_edit_mode=True,
        llm_backend="anthropic",
    )
    assert second.metrics["loop_watchdog_safe_mode_active"] is True
    assert second.metrics["loop_watchdog_safe_mode_triggered"] is False
    assert second.metrics["loop_watchdog_stop_flag"] is True
    assert int(second.metrics["loop_watchdog_safe_mode_failure_streak"]) >= 2

    events = read_events(sessions_root / "session-702" / "events.jsonl")
    assert any(str(row.get("tool", "")) == "loop_watchdog" for row in events)
