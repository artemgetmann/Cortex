from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from tracks.cli_sqlite import agent_runtime_context as runtime_context
from tracks.cli_sqlite.skill_routing_cli import SkillManifestEntry


class _FakeAdapter:
    @property
    def executor_tool_name(self) -> str:
        return "run_sqlite"

    def quality_keywords(self) -> re.Pattern[str]:
        return re.compile(r".", re.IGNORECASE)

    def docs_manifest(self) -> list[Any]:
        return []

    def system_prompt_fragment(self) -> str:
        return "adapter-fragment\n"

    def tool_defs(self, fixture_refs: list[str], *, opaque: bool) -> list[dict[str, Any]]:
        return [
            {"name": "read_skill", "input_schema": {"type": "object"}},
            {"name": "run_sqlite", "input_schema": {"type": "object"}},
        ]


def test_build_runtime_prompt_context_bootstrap_strips_read_skill_and_keeps_v2_block(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    entry = SkillManifestEntry(
        skill_ref="sqlite/demo",
        title="Demo",
        description="Demo",
        path=str(tmp_path / "skills" / "sqlite" / "demo" / "SKILL.md"),
        version=1,
        last_updated="2026-02-16T00:00:00+00:00",
        confidence=0.8,
    )
    monkeypatch.setattr(runtime_context, "build_skill_manifest", lambda **kwargs: [entry])
    monkeypatch.setattr(runtime_context, "route_manifest_entries", lambda **kwargs: [entry])
    monkeypatch.setattr(runtime_context, "manifest_summaries_text", lambda entries: "skills-summary")
    monkeypatch.setattr(runtime_context, "load_relevant_lessons", lambda **kwargs: ("legacy-lessons", 1))
    monkeypatch.setattr(runtime_context, "migrate_legacy_lessons", lambda **kwargs: None)
    monkeypatch.setattr(runtime_context, "retrieve_pre_run", lambda **kwargs: ([{"id": "m1"}], {}))

    context = runtime_context.build_runtime_prompt_context(
        task_id="demo_task",
        task=None,
        domain="sqlite",
        adapter=_FakeAdapter(),
        track_root=tmp_path,
        tasks_root=tmp_path / "tasks",
        skills_root=tmp_path / "skills",
        manifest_path=tmp_path / "skills" / "skills_manifest.json",
        lessons_path=tmp_path / "learning" / "lessons.jsonl",
        lessons_v2_path=tmp_path / "learning" / "lessons_v2.jsonl",
        fixture_refs=["fixture.csv", "task.md"],
        bootstrap=True,
        require_skill_read=True,
        opaque_tools=False,
        legacy_lessons_enabled=True,
        benchmark_placebo=False,
        runtime_candidate_policy_effective="anchored",
        runtime_contract={"required_tools": ["run_sqlite"]},
        llm_client=None,
        documentation=None,
        doc_mode="none",
        doc_retrieval="off",
        doc_budget_tokens=1200,
        doc_retriever_model=None,
        preload_docs_bundle=False,
        executor_docs=False,
        judge_docs=False,
        docs_prompt_max_chars=8000,
        executor_prompt_mode="full",
        load_task_text_fn=lambda _tasks_root, _task_id: "- Read the sqlite skill document.\nUse read_skill then solve.",
        prioritize_domain_routed_entries_fn=lambda **kwargs: kwargs["entries"],
        required_skill_refs_for_domain_fn=lambda **kwargs: {"sqlite/demo"},
        select_high_signal_prerun_matches_fn=lambda **kwargs: kwargs["matches"],
        format_v2_lesson_block_fn=lambda *args, **kwargs: ("Memory V2 lessons (high-signal):\n- lsn", ["lsn"]),
        format_legacy_placebo_lesson_block_fn=lambda **kwargs: "placebo-lessons",
        build_system_prompt_fn=lambda **kwargs: (
            f"skills={kwargs['skills_text']}\n"
            f"lessons={kwargs['lessons_text']}\n"
            f"domain={kwargs['domain_fragment']}"
        ),
        build_contract_execution_guidance_fn=lambda **kwargs: "contract-checklist",
        build_sqlite_validator_guidance_fn=lambda **kwargs: "validator-guidance",
        build_skill_manifest_fn=runtime_context.build_skill_manifest,
        route_manifest_entries_fn=runtime_context.route_manifest_entries,
        manifest_summaries_text_fn=runtime_context.manifest_summaries_text,
        load_relevant_lessons_fn=runtime_context.load_relevant_lessons,
        migrate_legacy_lessons_fn=runtime_context.migrate_legacy_lessons,
        retrieve_pre_run_fn=runtime_context.retrieve_pre_run,
        load_lesson_objects_fn=runtime_context.load_lesson_objects,
        build_documentation_bundle_fn=runtime_context.build_documentation_bundle,
    )

    assert "read_skill" not in context.task_text
    assert context.required_skill_refs == set()
    assert [tool["name"] for tool in context.tools] == ["run_sqlite"]
    assert "Memory V2 lessons (high-signal):" in context.lessons_text
    assert "contract-checklist" in context.system_prompt
    assert context.docs_bundle is None
