from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tracks.cli_sqlite import agent_cli
from tracks.cli_sqlite.domain_adapter import DomainWorkspace, ToolResult
from tracks.cli_sqlite.judge_llm import JudgeResult
from tracks.cli_sqlite.memory_cli import read_events


class _FakeUsage:
    def model_dump(self) -> dict[str, Any]:
        return {}


class _FakeBlock:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def model_dump(self) -> dict[str, Any]:
        return dict(self._payload)


class _FakeResponse:
    def __init__(self, content: list[dict[str, Any]]) -> None:
        self.usage = _FakeUsage()
        self.content = [_FakeBlock(block) for block in content]


class _FakeMessages:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = responses
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


class _RetryAdapter:
    def __init__(self) -> None:
        self.execute_calls: list[dict[str, Any]] = []

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
            return ToolResult(error=f"unknown tool {tool_name}")
        self.execute_calls.append(dict(tool_input))
        return ToolResult(output="ok")

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
        return "Test adapter.\n"

    def quality_keywords(self) -> re.Pattern[str]:
        return re.compile(r".")

    def build_alias_map(self, *, opaque: bool) -> dict[str, str]:
        del opaque
        return {}

    def docs_manifest(self) -> list[Any]:
        return []


def _tool_use_response(*, tool_use_id: str, tool_input: dict[str, Any]) -> _FakeResponse:
    return _FakeResponse(
        [
            {
                "type": "tool_use",
                "id": tool_use_id,
                "name": "run_sqlite",
                "input": tool_input,
            }
        ]
    )


def _configure_retry_harness(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    responses: list[_FakeResponse],
) -> tuple[Path, _RetryAdapter]:
    track_root = tmp_path / "track"
    tasks_root = track_root / "tasks"
    learning_root = track_root / "learning"
    sessions_root = track_root / "sessions"
    task_dir = tasks_root / "retry_task"
    task_dir.mkdir(parents=True, exist_ok=True)
    task_dir.joinpath("task.md").write_text("retry task", encoding="utf-8")

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

    adapter = _RetryAdapter()
    monkeypatch.setattr(agent_cli, "_resolve_adapter_with_mode", lambda *args, **kwargs: adapter)
    monkeypatch.setattr(agent_cli.anthropic, "Anthropic", lambda **kwargs: _FakeAnthropicClient(responses))
    monkeypatch.setattr(agent_cli, "build_skill_manifest", lambda **kwargs: [])
    monkeypatch.setattr(agent_cli, "load_relevant_lessons", lambda **kwargs: ("", 0))
    monkeypatch.setattr(agent_cli, "load_lesson_objects", lambda **kwargs: [])
    monkeypatch.setattr(agent_cli, "migrate_legacy_lessons", lambda **kwargs: None)
    monkeypatch.setattr(agent_cli, "retrieve_pre_run", lambda **kwargs: ([], []))
    monkeypatch.setattr(agent_cli, "llm_judge", lambda **kwargs: JudgeResult(passed=True, score=1.0, reasons=["ok"], raw_response="{}"))
    return sessions_root, adapter


def _collect_user_text_messages(messages: list[dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    for message in messages:
        if message.get("role") != "user":
            continue
        content = message.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    texts.append(text)
    return texts


def test_validation_retries_repeat_same_step_without_advancing_counter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    responses = [
        _tool_use_response(tool_use_id="tool-1", tool_input={"bad": "payload"}),
        _tool_use_response(tool_use_id="tool-2", tool_input={"bad": "payload"}),
        _tool_use_response(tool_use_id="tool-3", tool_input={"sql": "SELECT 1;"}),
    ]
    sessions_root, adapter = _configure_retry_harness(monkeypatch, tmp_path, responses)
    cfg = SimpleNamespace(anthropic_api_key="test-key")

    result = agent_cli.run_cli_agent(
        cfg=cfg,
        task_id="retry_task",
        task=None,
        session_id=601,
        max_steps=1,
        domain="sqlite",
        posttask_learn=False,
        require_skill_read=False,
    )

    events = read_events(sessions_root / "session-601" / "events.jsonl")
    assert [int(event.get("step", 0)) for event in events] == [1, 1, 1]
    assert result.metrics["steps"] == 1
    assert result.metrics["tool_validation_errors"] == 2
    assert result.metrics["tool_validation_retry_attempts"] == 2
    assert result.metrics["tool_validation_retry_capped_events"] == 0
    assert adapter.execute_calls == [{"sql": "SELECT 1;"}]


def test_validation_retry_cap_records_metric_and_queues_reflection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    responses = [
        _tool_use_response(tool_use_id="tool-1", tool_input={"bad": "payload"}),
        _tool_use_response(tool_use_id="tool-2", tool_input={"bad": "payload"}),
        _tool_use_response(tool_use_id="tool-3", tool_input={"bad": "payload"}),
        _tool_use_response(tool_use_id="tool-4", tool_input={"sql": "SELECT 1;"}),
    ]
    sessions_root, adapter = _configure_retry_harness(monkeypatch, tmp_path, responses)
    cfg = SimpleNamespace(anthropic_api_key="test-key")

    result = agent_cli.run_cli_agent(
        cfg=cfg,
        task_id="retry_task",
        task=None,
        session_id=602,
        max_steps=2,
        domain="sqlite",
        posttask_learn=False,
        require_skill_read=False,
    )

    events = read_events(sessions_root / "session-602" / "events.jsonl")
    assert [int(event.get("step", 0)) for event in events] == [1, 1, 1, 2]
    assert result.metrics["steps"] == 2
    assert result.metrics["tool_validation_errors"] == 3
    assert result.metrics["tool_validation_retry_attempts"] == 2
    assert result.metrics["tool_validation_retry_capped_events"] == 1
    assert result.metrics["v2_reflection_prompts"] >= 1
    assert any(
        row.get("reason") == "validation_retry_cap"
        for row in result.metrics.get("v2_reflection_reasons", [])
    )
    assert any("Trigger: validation_retry_cap." in text for text in _collect_user_text_messages(result.messages))
    assert adapter.execute_calls == [{"sql": "SELECT 1;"}]
