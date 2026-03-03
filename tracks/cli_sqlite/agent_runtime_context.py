from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from tracks.cli_sqlite.docs_pipeline import DocumentationBundle, build_documentation_bundle
from tracks.cli_sqlite.domain_adapter import DomainAdapter
from tracks.cli_sqlite.lesson_retrieval_v2 import retrieve_pre_run
from tracks.cli_sqlite.lesson_store_v2 import migrate_legacy_lessons
from tracks.cli_sqlite.learning_cli import load_lesson_objects, load_relevant_lessons
from tracks.cli_sqlite.skill_routing_cli import (
    SkillManifestEntry,
    build_skill_manifest,
    manifest_summaries_text,
    route_manifest_entries,
)


@dataclass
class RuntimePromptContext:
    task_text: str
    skills_text: str
    lessons_text: str
    system_prompt: str
    tools: list[dict[str, Any]]
    routed_entries: list[SkillManifestEntry]
    routed_refs: list[str]
    required_skill_refs: set[str]
    lessons_loaded: int
    prerun_v2_matches: list[Any]
    prerun_v2_ids: list[str]
    loaded_lesson_objects: list[Any]
    docs_bundle: DocumentationBundle | None
    docs_executor_block: str
    docs_judge_block: str
    docs_prompt_available: bool
    docs_selected_source_ids: list[str]
    docs_read_error_entries: list[dict[str, Any]]


def build_runtime_prompt_context(
    *,
    task_id: str,
    task: str | None,
    domain: str,
    adapter: DomainAdapter,
    track_root: Path,
    tasks_root: Path,
    skills_root: Path,
    manifest_path: Path,
    lessons_path: Path,
    lessons_v2_path: Path,
    fixture_refs: list[str],
    bootstrap: bool,
    require_skill_read: bool,
    opaque_tools: bool,
    legacy_lessons_enabled: bool,
    benchmark_placebo: bool,
    runtime_candidate_policy_effective: str,
    runtime_contract: dict[str, Any] | None,
    llm_client: Any | None,
    documentation: list[str] | None,
    doc_mode: str,
    doc_retrieval: str,
    doc_budget_tokens: int,
    doc_retriever_model: str | None,
    preload_docs_bundle: bool,
    executor_docs: bool,
    judge_docs: bool,
    docs_prompt_max_chars: int,
    executor_prompt_mode: str,
    load_task_text_fn: Callable[[Path, str], str],
    prioritize_domain_routed_entries_fn: Callable[..., list[SkillManifestEntry]],
    required_skill_refs_for_domain_fn: Callable[..., set[str]],
    select_high_signal_prerun_matches_fn: Callable[..., list[Any]],
    format_v2_lesson_block_fn: Callable[..., tuple[str, list[str]]],
    format_legacy_placebo_lesson_block_fn: Callable[..., str],
    build_system_prompt_fn: Callable[..., str],
    build_contract_execution_guidance_fn: Callable[..., str],
    build_sqlite_validator_guidance_fn: Callable[..., str],
    build_skill_manifest_fn: Callable[..., list[SkillManifestEntry]],
    route_manifest_entries_fn: Callable[..., list[SkillManifestEntry]],
    manifest_summaries_text_fn: Callable[[list[SkillManifestEntry]], str],
    load_relevant_lessons_fn: Callable[..., tuple[str, int]],
    migrate_legacy_lessons_fn: Callable[..., None],
    retrieve_pre_run_fn: Callable[..., tuple[list[Any], Any]],
    load_lesson_objects_fn: Callable[..., list[Any]],
    build_documentation_bundle_fn: Callable[..., DocumentationBundle],
) -> RuntimePromptContext:
    # Keep task resolution in one place so preview/runtime render identical user
    # input once flags (bootstrap, mode) are applied.
    task_text = task.strip() if isinstance(task, str) and task.strip() else load_task_text_fn(tasks_root, task_id)
    if bootstrap:
        task_text = re.sub(r"- Read the .*?skill document.*?\n", "", task_text)
        task_text = re.sub(r",?\s*read_skill,?", "", task_text)

    skill_manifest_entries = build_skill_manifest_fn(skills_root=skills_root, manifest_path=manifest_path)
    if bootstrap:
        routed_entries: list[SkillManifestEntry] = []
        routed_refs: list[str] = []
        required_skill_refs: set[str] = set()
        skills_text = (
            "(bootstrap mode — no skill docs available, ignore any task instructions about reading skills. "
            "Learn from trial, error messages, and prior lessons below.)"
        )
    else:
        routed_entries = route_manifest_entries_fn(task=task_text, entries=skill_manifest_entries, top_k=2)
        routed_entries = prioritize_domain_routed_entries_fn(entries=routed_entries, domain=domain)
        routed_refs = [entry.skill_ref for entry in routed_entries]
        required_skill_refs = required_skill_refs_for_domain_fn(
            routed_refs=routed_refs,
            domain=domain,
            require_skill_read=require_skill_read,
            task_id=task_id,
        )
        skills_text = manifest_summaries_text_fn(routed_entries)

    domain_keywords = adapter.quality_keywords()
    if legacy_lessons_enabled:
        lessons_text, lessons_loaded = load_relevant_lessons_fn(
            path=lessons_path,
            task_id=task_id,
            task=task_text,
            max_lessons=12,
            max_sessions=8,
            domain_keywords=domain_keywords,
        )
    else:
        lessons_text, lessons_loaded = "No prior lessons loaded.", 0

    # Keep migration in-context: retrieval behavior expects v1 lessons copied
    # into v2 first, and the migration itself is idempotent.
    migrate_legacy_lessons_fn(legacy_path=lessons_path, v2_path=lessons_v2_path)
    prerun_v2_matches, _ = retrieve_pre_run_fn(
        path=lessons_v2_path,
        task_id=task_id,
        domain=domain,
        task_text=task_text,
        max_results=8,
        candidate_policy=runtime_candidate_policy_effective,
    )
    prerun_v2_matches = select_high_signal_prerun_matches_fn(
        matches=prerun_v2_matches,
        task_id=task_id,
        domain=domain,
        max_results=4,
        min_score=0.55,
    )
    prerun_v2_block, prerun_v2_ids = format_v2_lesson_block_fn(
        prerun_v2_matches,
        use_placebo=benchmark_placebo,
        task_id=task_id,
        domain=domain,
    )
    loaded_lesson_objects = (
        load_lesson_objects_fn(
            path=lessons_path,
            task_id=task_id,
            domain_keywords=domain_keywords,
        )
        if legacy_lessons_enabled
        else []
    )
    if benchmark_placebo and lessons_loaded > 0:
        lessons_text = format_legacy_placebo_lesson_block_fn(
            lessons=loaded_lesson_objects,
            lessons_loaded=lessons_loaded,
            task_id=task_id,
            domain=domain,
        )
    if prerun_v2_block:
        lessons_text = f"{lessons_text}\n\n{prerun_v2_block}".strip()

    docs_bundle: DocumentationBundle | None = None
    docs_executor_block = ""
    docs_judge_block = ""
    docs_prompt_available = False
    docs_selected_source_ids: list[str] = []
    docs_read_error_entries: list[dict[str, Any]] = []
    if preload_docs_bundle:
        docs_bundle = build_documentation_bundle_fn(
            task_text=task_text,
            track_root=track_root,
            docs_manifest=adapter.docs_manifest(),
            documentation=documentation,
            mode=doc_mode,
            retrieval_mode=doc_retrieval,
            budget_tokens=doc_budget_tokens,
            retriever_model=doc_retriever_model,
            llm_client=llm_client,
            max_chunks=10,
        )
        docs_executor_block = docs_bundle.render_for_prompt(max_chars=docs_prompt_max_chars) if executor_docs else ""
        docs_judge_block = docs_bundle.render_for_prompt(max_chars=docs_prompt_max_chars) if judge_docs else ""
        docs_prompt_available = bool(docs_bundle.brief.strip())
        docs_selected_source_ids = sorted({chunk.source_id for chunk in docs_bundle.selected_chunks})
        docs_read_error_entries = [dict(row) for row in docs_bundle.load_errors]

    domain_fragment = adapter.system_prompt_fragment()
    contract_checklist_guidance = build_contract_execution_guidance_fn(
        contract=runtime_contract or {},
        max_required=4,
        max_forbidden=2,
    )
    validator_guidance = (
        build_sqlite_validator_guidance_fn(
            contract=runtime_contract or {},
            max_queries=4,
        )
        if domain == "sqlite"
        else ""
    )
    guidance_chunks = [chunk for chunk in (contract_checklist_guidance, validator_guidance) if chunk]
    if guidance_chunks:
        domain_fragment = f"{domain_fragment}\n" + "\n\n".join(guidance_chunks) + "\n"
    if bootstrap:
        domain_fragment = re.sub(
            r"- Before starting.*?do not guess or invent skill_ref names\.\n",
            "",
            domain_fragment,
            flags=re.DOTALL,
        )

    system_prompt = build_system_prompt_fn(
        task_id=task_id,
        skills_text=skills_text,
        lessons_text=lessons_text,
        domain_fragment=domain_fragment,
        executor_prompt_mode=executor_prompt_mode,
    )
    if docs_executor_block:
        system_prompt += f"\n\n{docs_executor_block}\n"
    if required_skill_refs:
        executor_tool = adapter.executor_tool_name
        system_prompt += (
            "\nSkill gate requirement:\n"
            f"- Before first {executor_tool} call, read at least one of: {sorted(required_skill_refs)}\n"
        )
    if opaque_tools:
        system_prompt += "\nTool names are opaque. Read your routed skills for usage semantics.\n"

    tools = adapter.tool_defs(fixture_refs, opaque=opaque_tools)
    if bootstrap:
        read_skill_api_name = "read_skill" if not opaque_tools else "probe"
        tools = [tool for tool in tools if tool.get("name") != read_skill_api_name]

    return RuntimePromptContext(
        task_text=task_text,
        skills_text=skills_text,
        lessons_text=lessons_text,
        system_prompt=system_prompt,
        tools=tools,
        routed_entries=routed_entries,
        routed_refs=routed_refs,
        required_skill_refs=required_skill_refs,
        lessons_loaded=int(lessons_loaded),
        prerun_v2_matches=list(prerun_v2_matches),
        prerun_v2_ids=list(prerun_v2_ids),
        loaded_lesson_objects=list(loaded_lesson_objects),
        docs_bundle=docs_bundle,
        docs_executor_block=docs_executor_block,
        docs_judge_block=docs_judge_block,
        docs_prompt_available=bool(docs_prompt_available),
        docs_selected_source_ids=list(docs_selected_source_ids),
        docs_read_error_entries=list(docs_read_error_entries),
    )
