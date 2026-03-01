from __future__ import annotations

import json
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


class _FakeRetrievalMatch:
    def __init__(
        self,
        *,
        lesson_id: str,
        rule_text: str,
        lane: str = "strict",
        gap_signature: str = "",
    ) -> None:
        self.lesson = SimpleNamespace(
            lesson_id=lesson_id,
            rule_text=rule_text,
            gap_signature=gap_signature,
        )
        self.lane = lane


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


def _lesson_row(
    text: str,
    *,
    trigger_gap_signature: str = "",
    action_template: str = "",
    expected_evidence: str = "",
    reason_code: str = "",
    gap_type: str = "",
) -> Any:
    return SimpleNamespace(
        lesson=text,
        category="negative",
        confidence=0.9,
        source="model",
        trigger_gap_signature=trigger_gap_signature,
        action_template=action_template,
        expected_evidence=expected_evidence,
        reason_code=reason_code,
        gap_type=gap_type,
    )


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

    def deterministic_gap_recipes(
        self,
        *,
        task_id: str,
        unresolved_gaps: list[dict[str, Any]],
        max_items: int = 3,
    ) -> list[str]:
        del task_id
        # Keep this fake adapter explicit: tests can verify core wiring while
        # domain-specific recipe content lives outside the orchestrator.
        rows: list[str] = []
        for gap in unresolved_gaps:
            if not isinstance(gap, dict):
                continue
            if str(gap.get("reason_code", "")).strip() != "required_query_mismatch":
                continue
            sql = str(gap.get("query_sql", "")).strip()
            if not sql:
                continue
            rows.append(f"run_sqlite(sql=\"{sql}\")")
            if len(rows) >= max(1, int(max_items)):
                break
        return rows


class _SequencedRetryAdapter(_RetryAdapter):
    def __init__(self, results: list[ToolResult]) -> None:
        super().__init__()
        self._results = list(results)

    def execute(self, tool_name: str, tool_input: dict[str, Any], workspace: DomainWorkspace) -> ToolResult:
        del workspace
        if tool_name != "run_sqlite":
            return ToolResult(error=f"unknown tool {tool_name}")
        self.execute_calls.append(dict(tool_input))
        idx = len(self.execute_calls) - 1
        if idx < len(self._results):
            return self._results[idx]
        return ToolResult(output="ok")


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
    adapter: _RetryAdapter | None = None,
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

    adapter = adapter or _RetryAdapter()
    monkeypatch.setattr(agent_cli, "_resolve_adapter_with_mode", lambda *args, **kwargs: adapter)
    monkeypatch.setattr(agent_cli.anthropic, "Anthropic", lambda **kwargs: _FakeAnthropicClient(responses))
    monkeypatch.setattr(agent_cli, "build_skill_manifest", lambda **kwargs: [])
    monkeypatch.setattr(agent_cli, "load_relevant_lessons", lambda **kwargs: ("", 0))
    monkeypatch.setattr(agent_cli, "load_lesson_objects", lambda **kwargs: [])
    monkeypatch.setattr(agent_cli, "migrate_legacy_lessons", lambda **kwargs: None)
    monkeypatch.setattr(agent_cli, "retrieve_pre_run", lambda **kwargs: ([], []))
    monkeypatch.setattr(
        agent_cli,
        "llm_judge",
        lambda **kwargs: JudgeResult(
            passed=True,
            score=1.0,
            reasons=["ok"],
            doc_grounding=[],
            raw_response="{}",
        ),
    )
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
        llm_backend="anthropic",
    )

    events = read_events(sessions_root / "session-601" / "events.jsonl")
    assert [int(event.get("step", 0)) for event in events] == [1, 1, 1]
    assert result.metrics["steps"] == 1
    assert result.metrics["tool_validation_errors"] == 2
    assert result.metrics["tool_validation_retry_attempts"] == 2
    assert result.metrics["tool_validation_retry_capped_events"] == 0
    assert result.metrics["error_count"] == (
        result.metrics["tool_errors"]
        + result.metrics["tool_validation_errors"]
        + result.metrics["v2_error_events"]
    )
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
        llm_backend="anthropic",
    )

    events = read_events(sessions_root / "session-602" / "events.jsonl")
    assert [int(event.get("step", 0)) for event in events] == [1, 1, 1, 2]
    assert result.metrics["steps"] == 2
    assert result.metrics["tool_validation_errors"] == 3
    assert result.metrics["tool_validation_retry_attempts"] == 2
    assert result.metrics["tool_validation_retry_capped_events"] == 1
    assert result.metrics["error_count"] == (
        result.metrics["tool_errors"]
        + result.metrics["tool_validation_errors"]
        + result.metrics["v2_error_events"]
    )
    assert result.metrics["v2_reflection_prompts"] >= 1
    assert any(
        row.get("reason") == "validation_retry_cap"
        for row in result.metrics.get("v2_reflection_reasons", [])
    )
    assert any("Trigger: validation_retry_cap." in text for text in _collect_user_text_messages(result.messages))
    assert adapter.execute_calls == [{"sql": "SELECT 1;"}]


def test_repeated_dependency_setup_failures_trigger_fallback_reflection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    responses = [
        _tool_use_response(tool_use_id="tool-1", tool_input={"sql": "SELECT 1;"}),
        _tool_use_response(tool_use_id="tool-2", tool_input={"sql": "SELECT 1;"}),
        _tool_use_response(tool_use_id="tool-3", tool_input={"sql": "SELECT 1;"}),
    ]
    adapter = _SequencedRetryAdapter(
        [
            ToolResult(error="ModuleNotFoundError: No module named 'openpyxl'"),
            ToolResult(error="ModuleNotFoundError: No module named 'openpyxl'"),
            ToolResult(output="ok"),
        ]
    )
    sessions_root, _ = _configure_retry_harness(monkeypatch, tmp_path, responses, adapter=adapter)
    cfg = SimpleNamespace(anthropic_api_key="test-key")

    result = agent_cli.run_cli_agent(
        cfg=cfg,
        task_id="retry_task",
        task=None,
        session_id=603,
        max_steps=3,
        domain="shell",
        posttask_learn=False,
        require_skill_read=False,
        llm_backend="anthropic",
    )

    events = read_events(sessions_root / "session-603" / "events.jsonl")
    assert [int(event.get("step", 0)) for event in events] == [1, 2, 3]
    assert result.metrics["v2_dependency_fallback_checks"] == 1
    assert any(
        row.get("reason") == "dependency_setup_repeat"
        for row in result.metrics.get("v2_reflection_reasons", [])
    )
    reflection_texts = [
        text for text in _collect_user_text_messages(result.messages)
        if "Trigger: dependency_setup_repeat." in text
    ]
    assert reflection_texts
    assert "Deterministic fallback check:" in reflection_texts[0]
    assert "pip install" not in reflection_texts[0]


def test_contract_gap_checker_injects_one_retry_before_stop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    responses = [
        _FakeResponse([{"type": "text", "text": "done"}]),
        _tool_use_response(tool_use_id="tool-1", tool_input={"sql": "SELECT 1;"}),
    ]
    sessions_root, adapter = _configure_retry_harness(monkeypatch, tmp_path, responses)
    task_dir = Path(agent_cli.TASKS_ROOT) / "retry_task"
    contract_payload = {
        "id": "retry-contract-v1",
        "task_match": {"all": ["retry"], "any": []},
        "signals": {
            "required_event_patterns": ["tool=run_sqlite"],
            "forbidden_event_patterns": [],
            "required_queries": [],
            "required_sql_patterns": [],
            "forbidden_sql_patterns": [],
            "required_files": [],
            "max_error_count": 0,
        },
    }
    task_dir.joinpath("CONTRACT.json").write_text(json.dumps(contract_payload), encoding="utf-8")
    cfg = SimpleNamespace(anthropic_api_key="test-key")

    result = agent_cli.run_cli_agent(
        cfg=cfg,
        task_id="retry_task",
        task=None,
        session_id=604,
        max_steps=1,
        domain="sqlite",
        posttask_learn=False,
        require_skill_read=False,
        llm_backend="anthropic",
        contract_gap_retry=True,
        contract_gap_retry_steps=1,
    )

    events = read_events(sessions_root / "session-604" / "events.jsonl")
    tools = [str(event.get("tool", "")) for event in events]
    assert "contract_gap_retry" in tools
    assert "run_sqlite" in tools
    assert result.metrics["contract_gap_retry_attempts"] == 1
    assert result.metrics["contract_gap_retry_triggered"] == 1
    assert result.metrics["contract_gap_unresolved_count_prestop"] >= 1
    assert result.metrics["contract_gap_unresolved_count_final"] == 0
    assert any(
        "Deterministic contract gap check found unresolved requirements." in text
        for text in _collect_user_text_messages(result.messages)
    )
    assert adapter.execute_calls == [{"sql": "SELECT 1;"}]


def test_contract_gap_checker_triggers_at_step_cap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    responses = [
        _tool_use_response(tool_use_id="tool-1", tool_input={"sql": "SELECT 1;"}),
        _FakeResponse([{"type": "text", "text": "done"}]),
    ]
    sessions_root, adapter = _configure_retry_harness(monkeypatch, tmp_path, responses)
    task_dir = Path(agent_cli.TASKS_ROOT) / "retry_task"
    contract_payload = {
        "id": "retry-contract-step-cap-v1",
        "task_match": {"all": ["retry"], "any": []},
        "signals": {
            "required_event_patterns": [
                "tool=run_sqlite",
                "tool=contract_gap_retry",
            ],
            "forbidden_event_patterns": [],
            "required_queries": [],
            "required_sql_patterns": [],
            "forbidden_sql_patterns": [],
            "required_files": [],
            "max_error_count": 0,
        },
    }
    task_dir.joinpath("CONTRACT.json").write_text(json.dumps(contract_payload), encoding="utf-8")
    cfg = SimpleNamespace(anthropic_api_key="test-key")

    result = agent_cli.run_cli_agent(
        cfg=cfg,
        task_id="retry_task",
        task=None,
        session_id=605,
        max_steps=1,
        domain="sqlite",
        posttask_learn=False,
        require_skill_read=False,
        llm_backend="anthropic",
        contract_gap_retry=True,
        contract_gap_retry_steps=1,
    )

    events = read_events(sessions_root / "session-605" / "events.jsonl")
    retry_rows = [row for row in events if str(row.get("tool", "")) == "contract_gap_retry"]
    assert retry_rows
    assert str(retry_rows[0].get("tool_input", {}).get("trigger", "")) == "step_cap"
    assert result.metrics["contract_gap_retry_attempts"] == 1
    assert result.metrics["contract_gap_retry_triggered"] == 1
    assert result.metrics["contract_gap_unresolved_count_prestop"] >= 1
    assert result.metrics["eval_passed"] is True
    assert adapter.execute_calls == [{"sql": "SELECT 1;"}]


def test_contract_gap_retry_counts_gap_lesson_activations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    responses = [
        _FakeResponse([{"type": "text", "text": "done"}]),
        _tool_use_response(tool_use_id="tool-1", tool_input={"sql": "SELECT 1;"}),
    ]
    sessions_root, adapter = _configure_retry_harness(monkeypatch, tmp_path, responses)
    task_dir = Path(agent_cli.TASKS_ROOT) / "retry_task"
    contract_payload = {
        "id": "retry-contract-gap-activation-v1",
        "task_match": {"all": ["retry"], "any": []},
        "signals": {
            "required_event_patterns": ["tool=run_sqlite"],
            "forbidden_event_patterns": [],
            "required_queries": [],
            "required_sql_patterns": [],
            "forbidden_sql_patterns": [],
            "required_files": [],
            "max_error_count": 0,
        },
    }
    task_dir.joinpath("CONTRACT.json").write_text(json.dumps(contract_payload), encoding="utf-8")
    monkeypatch.setattr(
        agent_cli,
        "retrieve_on_error",
        lambda **kwargs: (
                [
                    _FakeRetrievalMatch(
                        lesson_id="lsn_gap_1",
                        rule_text="When contract gap remains, run one corrective write then verify output.",
                        lane="strict",
                        gap_signature="missing_required_event_pattern|required_event_pattern|tool=run_sqlite",
                    )
                ],
                [],
            ),
        )
    cfg = SimpleNamespace(anthropic_api_key="test-key")

    result = agent_cli.run_cli_agent(
        cfg=cfg,
        task_id="retry_task",
        task=None,
        session_id=606,
        max_steps=1,
        domain="sqlite",
        posttask_learn=False,
        require_skill_read=False,
        llm_backend="anthropic",
        contract_gap_retry=True,
        contract_gap_retry_steps=1,
    )

    assert result.metrics["contract_gap_retry_attempts"] == 1
    assert result.metrics["v2_lesson_activations"] >= 1
    assert result.metrics["lesson_activations"] >= 1
    assert adapter.execute_calls == [{"sql": "SELECT 1;"}]


def test_deterministic_gap_fix_recipes_sqlite_emit_command_recipe() -> None:
    recipes = agent_cli._deterministic_gap_fix_recipes(
        adapter=_RetryAdapter(),
        domain="sqlite",
        task_id="retry_task",
        unresolved_gaps=[
            {
                "reason_code": "required_query_mismatch",
                "gap_type": "required_query",
                "query_id": "reject_count",
                "query_sql": "SELECT COUNT(*) AS c FROM rejects;",
                "expected_rows": [["1"]],
            }
        ],
        max_items=3,
    )

    assert recipes
    assert recipes[0].startswith("[deterministic_recipe domain=sqlite task_id=retry_task]")
    assert "run_sqlite(sql=" in recipes[0]
    assert "SELECT COUNT(*) AS c FROM rejects;" in recipes[0]


def test_contract_gap_retry_injects_deterministic_recipe_hints(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    responses = [
        _FakeResponse([{"type": "text", "text": "done"}]),
        _tool_use_response(tool_use_id="tool-1", tool_input={"sql": "SELECT 1;"}),
    ]
    sessions_root, adapter = _configure_retry_harness(monkeypatch, tmp_path, responses)
    task_dir = Path(agent_cli.TASKS_ROOT) / "retry_task"
    contract_payload = {
        "id": "retry-contract-query-gap-v1",
        "task_match": {"all": ["retry"], "any": []},
        "signals": {
            "required_event_patterns": ["tool=run_sqlite"],
            "forbidden_event_patterns": [],
            "required_queries": [
                {
                    "id": "reject_count",
                    "sql": "SELECT COUNT(*) AS c FROM rejects;",
                    "expected_rows": [["1"]],
                }
            ],
            "required_sql_patterns": [],
            "forbidden_sql_patterns": [],
            "required_files": [],
            "max_error_count": 0,
        },
    }
    task_dir.joinpath("CONTRACT.json").write_text(json.dumps(contract_payload), encoding="utf-8")
    cfg = SimpleNamespace(anthropic_api_key="test-key")

    result = agent_cli.run_cli_agent(
        cfg=cfg,
        task_id="retry_task",
        task=None,
        session_id=607,
        max_steps=1,
        domain="sqlite",
        posttask_learn=False,
        require_skill_read=False,
        llm_backend="anthropic",
        contract_gap_retry=True,
        contract_gap_retry_steps=1,
    )

    retry_prompts = [
        text
        for text in _collect_user_text_messages(result.messages)
        if "Deterministic contract gap check found unresolved requirements." in text
    ]
    assert retry_prompts
    assert "Deterministic repair block (execute exactly):" in retry_prompts[0]
    assert "[deterministic_recipe domain=sqlite task_id=retry_task]" in retry_prompts[0]
    assert result.metrics["contract_gap_retry_attempts"] == 1
    assert result.metrics["contract_gap_deterministic_hint_count"] >= 1
    assert len(adapter.execute_calls) >= 2
    # First deterministic validator run happens before retry and the post-repair
    # validator runs again after one executor action to verify closure progress.
    assert any("SELECT COUNT(*) AS c FROM rejects;" in str(row.get("sql", "")) for row in adapter.execute_calls)
    assert any(row == {"sql": "SELECT 1;"} for row in adapter.execute_calls)
    assert result.metrics["contract_validator_postretry_runs"] == 1
    assert result.metrics["contract_validator_postretry_last_trigger"] == "post_retry_after_repair"
    assert result.metrics["contract_retry_repair_observed"] is True
    events = read_events(sessions_root / "session-607" / "events.jsonl")
    assert any(str(event.get("tool", "")) == "contract_gap_retry" for event in events)
    assert any(str(event.get("tool", "")) == "contract_validator_postretry" for event in events)


def test_posttask_structured_fallback_respects_det_recipe_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    responses = [
        _FakeResponse([{"type": "text", "text": "done"}]),
        _tool_use_response(tool_use_id="tool-1", tool_input={"sql": "SELECT 1;"}),
    ]
    sessions_root, _adapter = _configure_retry_harness(monkeypatch, tmp_path, responses)
    task_dir = Path(agent_cli.TASKS_ROOT) / "retry_task"
    contract_payload = {
        "id": "retry-contract-query-gap-v1",
        "task_match": {"all": ["retry"], "any": []},
        "signals": {
            "required_event_patterns": ["tool=run_sqlite"],
            "forbidden_event_patterns": [],
            "required_queries": [
                {
                    "id": "reject_count",
                    "sql": "SELECT COUNT(*) AS c FROM rejects;",
                    "expected_rows": [["1"]],
                }
            ],
            "required_sql_patterns": [],
            "forbidden_sql_patterns": [],
            "required_files": [],
            "max_error_count": 0,
        },
    }
    task_dir.joinpath("CONTRACT.json").write_text(json.dumps(contract_payload), encoding="utf-8")
    cfg = SimpleNamespace(anthropic_api_key="test-key")
    monkeypatch.setattr(
        agent_cli,
        "generate_lessons",
        lambda **kwargs: SimpleNamespace(raw_lessons=[], filtered_lessons=[]),
    )

    result = agent_cli.run_cli_agent(
        cfg=cfg,
        task_id="retry_task",
        task=None,
        session_id=608,
        max_steps=1,
        domain="sqlite",
        posttask_learn=True,
        require_skill_read=False,
        llm_backend="anthropic",
        contract_gap_retry=True,
        contract_gap_retry_steps=1,
        contract_gap_deterministic_recipes=False,
    )

    assert result.metrics["contract_gap_deterministic_hint_count"] == 0
    assert result.metrics["v2_structured_fallback_lessons"] == 0
    assert result.metrics["v2_lessons_generated"] == 0
    learning_artifacts = json.loads(
        (sessions_root / "session-608" / "learning_artifacts.json").read_text(encoding="utf-8")
    )
    assert learning_artifacts.get("lesson_candidates") == []


def test_posttask_v2_learning_runs_without_skill_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    responses = [_FakeResponse([{"type": "text", "text": "done"}])]
    sessions_root, _adapter = _configure_retry_harness(monkeypatch, tmp_path, responses)
    cfg = SimpleNamespace(anthropic_api_key="test-key")

    def _fake_generate_lessons(**kwargs: Any) -> Any:
        del kwargs
        row = _lesson_row("run_sqlite(sql=\"SELECT 1;\")")
        return SimpleNamespace(raw_lessons=[row], filtered_lessons=[row])

    monkeypatch.setattr(agent_cli, "generate_lessons", _fake_generate_lessons)
    monkeypatch.setattr(agent_cli, "store_lessons", lambda **kwargs: 0)
    monkeypatch.setattr(agent_cli, "prune_lessons", lambda *args, **kwargs: None)

    result = agent_cli.run_cli_agent(
        cfg=cfg,
        task_id="retry_task",
        task=None,
        session_id=609,
        max_steps=1,
        domain="sqlite",
        posttask_learn=True,
        structured_lessons_required=False,
        require_skill_read=False,
        llm_backend="anthropic",
        contract_gap_retry=False,
    )

    assert result.metrics["posttask_skill_patching_skip_reason"] == "no_skill_manifest"
    assert int(result.metrics["v2_lessons_generated"]) + int(result.metrics["v2_lessons_merged"]) >= 1
    learning_artifacts = json.loads(
        (sessions_root / "session-609" / "learning_artifacts.json").read_text(encoding="utf-8")
    )
    assert len(learning_artifacts.get("lesson_candidates") or []) >= 1


def test_validate_structured_model_lesson_requires_trigger_action_and_evidence() -> None:
    unresolved = [
        {
            "reason_code": "required_query_mismatch",
            "gap_type": "required_query",
            "gap_signature": "required_query_mismatch|required_query|reject_count",
        }
    ]
    allowed_tools = {"run_sqlite", "run_bash", "read_skill", "show_fixture"}

    missing_trigger = SimpleNamespace(
        trigger_gap_signature="",
        action_template='run_sqlite(sql="SELECT 1;")',
        expected_evidence='required_query:reject_count == [["1"]]',
        reason_code="required_query_mismatch",
        gap_type="required_query",
    )
    ok, reason, payload = agent_cli._validate_structured_model_lesson(
        lesson=missing_trigger,
        unresolved_gap_rows=unresolved,
        allowed_action_tools=allowed_tools,
    )
    assert ok is False
    assert reason == "missing_trigger_gap_signature"
    assert payload == {}

    invalid_action = SimpleNamespace(
        trigger_gap_signature="required_query_mismatch|required_query|reject_count",
        action_template='rm_rf(sql="DROP TABLE ledger;")',
        expected_evidence='required_query:reject_count == [["1"]]',
        reason_code="required_query_mismatch",
        gap_type="required_query",
    )
    ok2, reason2, payload2 = agent_cli._validate_structured_model_lesson(
        lesson=invalid_action,
        unresolved_gap_rows=unresolved,
        allowed_action_tools=allowed_tools,
    )
    assert ok2 is False
    assert reason2 == "invalid_action_template_tool"
    assert payload2 == {}

    placeholder_action = SimpleNamespace(
        trigger_gap_signature="required_query_mismatch|required_query|reject_count",
        action_template='run_sqlite(sql="...")',
        expected_evidence='required_query_mismatch|required_query|reject_count',
        reason_code="required_query_mismatch",
        gap_type="required_query",
    )
    ok_placeholder, reason_placeholder, payload_placeholder = agent_cli._validate_structured_model_lesson(
        lesson=placeholder_action,
        unresolved_gap_rows=unresolved,
        allowed_action_tools=allowed_tools,
    )
    assert ok_placeholder is False
    assert reason_placeholder == "invalid_action_template_placeholder"
    assert payload_placeholder == {}

    unanchored_evidence = SimpleNamespace(
        trigger_gap_signature="required_query_mismatch|required_query|reject_count",
        action_template='run_sqlite(sql="SELECT COUNT(*) FROM rejects;")',
        expected_evidence="looks good now",
        reason_code="required_query_mismatch",
        gap_type="required_query",
    )
    ok_unanchored, reason_unanchored, payload_unanchored = agent_cli._validate_structured_model_lesson(
        lesson=unanchored_evidence,
        unresolved_gap_rows=unresolved,
        allowed_action_tools=allowed_tools,
    )
    assert ok_unanchored is False
    assert reason_unanchored == "expected_evidence_unanchored"
    assert payload_unanchored == {}

    valid = SimpleNamespace(
        trigger_gap_signature="required_query_mismatch|required_query|reject_count",
        action_template='run_sqlite(sql="SELECT COUNT(*) FROM rejects;")',
        expected_evidence='required_query_mismatch|required_query|reject_count == [["1"]]',
        reason_code="required_query_mismatch",
        gap_type="required_query",
    )
    ok3, reason3, payload3 = agent_cli._validate_structured_model_lesson(
        lesson=valid,
        unresolved_gap_rows=unresolved,
        allowed_action_tools=allowed_tools,
    )
    assert ok3 is True
    assert reason3 == ""
    assert payload3["trigger_gap_signature"] == "required_query_mismatch|required_query|reject_count"
    assert payload3["action_template"].startswith("run_sqlite(")

    valid_shell_redirection = SimpleNamespace(
        trigger_gap_signature="required_query_mismatch|required_query|reject_count",
        action_template='run_bash(command="echo ok > out.txt")',
        expected_evidence='required_query_mismatch|required_query|reject_count',
        reason_code="required_query_mismatch",
        gap_type="required_query",
    )
    ok4, reason4, payload4 = agent_cli._validate_structured_model_lesson(
        lesson=valid_shell_redirection,
        unresolved_gap_rows=unresolved,
        allowed_action_tools=allowed_tools,
    )
    assert ok4 is True
    assert reason4 == ""
    assert payload4["action_template"].startswith("run_bash(")


def test_validate_structured_model_lesson_allows_semantic_anchor_from_gap_detail() -> None:
    unresolved = [
        {
            "reason_code": "missing_required_event_pattern",
            "gap_type": "required_event_pattern",
            "gap_signature": "missing_required_event_pattern|required_event_pattern|(?is)git\\\\s+format-patch",
            "detail": "(?is)git\\\\s+format-patch\\\\s+-1\\\\s+HEAD\\\\s+--stdout",
        }
    ]
    lesson = SimpleNamespace(
        trigger_gap_signature="missing_required_event_pattern|required_event_pattern|(?is)git\\\\s+format-patch",
        action_template='run_bash(command="git format-patch -1 HEAD --stdout > hotfix.patch")',
        expected_evidence="hotfix.patch created via git format-patch and present in task root",
        reason_code="missing_required_event_pattern",
        gap_type="required_event_pattern",
    )
    ok, reason, payload = agent_cli._validate_structured_model_lesson(
        lesson=lesson,
        unresolved_gap_rows=unresolved,
        allowed_action_tools={"run_bash"},
    )
    assert ok is True
    assert reason == ""
    assert payload["trigger_gap_signature"].startswith("missing_required_event_pattern|required_event_pattern")


def test_extract_action_template_from_legacy_shell_lesson() -> None:
    lesson_text = (
        "WRONG: source repo missing -> CORRECT: git init -b main source_repo. "
        "WHY: required event pattern git init source_repo missing"
    )
    action = agent_cli._extract_action_template_from_legacy_lesson(
        lesson_text=lesson_text,
        executor_tool_name="run_bash",
    )
    assert action == 'run_bash(command="git init -b main source_repo")'


def test_extract_action_template_from_legacy_sql_lesson() -> None:
    lesson_text = "WRONG: missing reject count -> CORRECT: SELECT COUNT(*) FROM rejects;"
    action = agent_cli._extract_action_template_from_legacy_lesson(
        lesson_text=lesson_text,
        executor_tool_name="run_sqlite",
    )
    assert action.startswith('run_sqlite(sql="SELECT COUNT(*) FROM rejects')
