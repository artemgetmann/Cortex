from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import anthropic

from claude_print_client import ClaudePrintClient
from claude_print_runtime import (
    DEFAULT_LLM_BACKEND,
    LLM_BACKENDS as SHARED_LLM_BACKENDS,
    clip_text,
    normalize_llm_backend,
)
from tracks.cli_sqlite.agent_runtime_context import build_runtime_prompt_context
from tracks.cli_sqlite.agent_transport_router import (
    create_executor_response_via_claude_print as _create_executor_response_via_claude_print,
    request_executor_turn,
)
from config import CortexConfig
from tracks.cli_sqlite.adapter_registry import resolve_adapter, resolve_adapter_with_mode
from tracks.cli_sqlite.domain_adapter import DomainAdapter, DomainWorkspace, ToolResult
from tracks.cli_sqlite.docs_pipeline import (
    build_documentation_bundle,
    normalize_doc_mode,
    normalize_doc_retrieval_mode,
    write_doc_artifacts,
)
from tracks.cli_sqlite import contract_gap_guidance as _contract_gap_guidance
from tracks.cli_sqlite import verification_runtime_helpers as _verification_runtime_helpers
from tracks.cli_sqlite import runtime_misc_helpers as _runtime_misc_helpers
from tracks.cli_sqlite import legacy_probe_helpers as _legacy_probe_helpers
from tracks.cli_sqlite import hotfix_closure_helpers as _hotfix_closure_helpers
from tracks.cli_sqlite import agent_policy_helpers as _agent_policy_helpers
from tracks.cli_sqlite.eval_cli import evaluate_cli_session, load_contract, unresolved_contract_gaps
from tracks.cli_sqlite.judge_llm import JudgeResult, default_judge_model, llm_judge
from tracks.cli_sqlite.knowledge_provider import LocalDocsKnowledgeProvider
from tracks.cli_sqlite.loop_watchdog import (
    LoopWatchdogDecision,
    LoopWatchdogSnapshot,
    LoopWatchdogState,
    evaluate_watchdog_policy,
    load_watchdog_state,
    next_watchdog_state,
    persist_watchdog_state,
    state_path_for_learning_root,
)
from tracks.cli_sqlite.error_capture import ErrorEvent, build_error_fingerprint, extract_tags
from tracks.cli_sqlite.lesson_promotion_v2 import LessonOutcome, apply_outcomes
from tracks.cli_sqlite import lesson_selection_policy as _lesson_selection_policy
from tracks.cli_sqlite.lesson_retrieval_v2 import (
    CANDIDATE_POLICY_ANCHORED,
    CANDIDATE_POLICY_PROMOTED_ONLY,
    DEFAULT_TRANSFER_MAX_RESULTS,
    DEFAULT_TRANSFER_SCORE_COEFFICIENT,
    TRANSFER_POLICY_ALWAYS,
    TRANSFER_POLICY_AUTO,
    TRANSFER_POLICY_OFF,
    retrieve_on_error,
    retrieve_pre_run,
)
from tracks.cli_sqlite.lesson_store_v2 import (
    LessonRecord,
    load_lesson_records,
    migrate_legacy_lessons,
    upsert_lesson_records,
)
from tracks.cli_sqlite.lesson_structured_validation import (
    _allowed_action_tools_for_adapter,
    _extract_action_template_from_legacy_lesson,
    _validate_structured_model_lesson,
)
from tracks.cli_sqlite.learning_cli import (
    find_lessons_for_error,
    generate_lessons,
    LessonGenerationResult,
    load_lesson_objects,
    load_relevant_lessons,
    prune_lessons,
    store_lessons,
)
from tracks.cli_sqlite.memory_cli import ensure_session, read_events, write_event, write_metrics
from tracks.cli_sqlite.no_tool_call_policy import (
    build_no_tool_recovery_prompt,
    record_no_tool_call_event,
    should_inject_no_tool_recovery_prompt,
)
from tracks.cli_sqlite.openai_transport import (
    OpenAICompatClient as _OpenAICompatClient,
)
from tracks.cli_sqlite.openai_agents_sdk_transport import (
    OpenAIAgentsSDKCompatClient as _OpenAIAgentsSDKCompatClient,
    OpenAIAgentsSDKExecutionState as _OpenAIAgentsSDKExecutionState,
)
from tracks.cli_sqlite.prompt_builder import (
    DEFAULT_EXECUTOR_PROMPT_MODE,
    build_executor_system_prompt,
    normalize_executor_prompt_mode,
)
from tracks.cli_sqlite.run_observability import (
    append_self_edit_gate_event,
    append_lifecycle_event,
    append_run_ledger_entry,
    build_run_id,
    format_utc_timestamp,
    normalize_error_summary,
)
from tracks.cli_sqlite.self_edit_gate import (
    apply_guarded_self_edit_updates,
    build_self_edit_manifest_entries,
    self_edit_allowed_refs,
)
from tracks.cli_sqlite.runtime_paths import resolve_runtime_paths
from tracks.cli_sqlite.self_improve_cli import (
    SkillUpdate,
    apply_skill_updates,
    auto_promote_queued_candidates,
    parse_reflection_response,
    propose_skill_updates,
    queue_skill_update_candidates,
    skill_digest,
)
from tracks.cli_sqlite.skill_routing_cli import (
    SkillManifestEntry,
    build_skill_manifest,
    manifest_summaries_text,
    resolve_skill_content,
    route_manifest_entries,
)
from tracks.cli_sqlite.tool_validation import build_tool_schema_map, validate_tool_input


TRACK_ROOT = Path(__file__).resolve().parent
SKILLS_ROOT = TRACK_ROOT / "skills"
MANIFEST_PATH = SKILLS_ROOT / "skills_manifest.json"
TASKS_ROOT = TRACK_ROOT / "tasks"
_RUNTIME_PATHS = resolve_runtime_paths(track_root=TRACK_ROOT)
LEARNING_ROOT = _RUNTIME_PATHS.learning_root
SESSIONS_ROOT = _RUNTIME_PATHS.sessions_root
LESSONS_PATH = _RUNTIME_PATHS.lessons_path
LESSONS_V2_PATH = _RUNTIME_PATHS.lessons_v2_path
MEMORY_EVENTS_PATH = _RUNTIME_PATHS.memory_events_path
QUEUE_PATH = _RUNTIME_PATHS.queue_path
PROMOTED_PATH = _RUNTIME_PATHS.promoted_path
ESCALATION_STATE_PATH = _RUNTIME_PATHS.escalation_state_path

DEFAULT_EXECUTOR_MODEL = "claude-haiku-4-5"
DEFAULT_CRITIC_MODEL = "claude-haiku-4-5"
SONNET_MODEL = "claude-sonnet-4-5"
OPUS_MODEL = "claude-opus-4-6"
OPENAI_DEFAULT_MODEL = "gpt-5-nano"
LLM_BACKENDS = tuple((*SHARED_LLM_BACKENDS, "openai", "openai_agents_sdk"))
READ_SKILL_TOOL_NAME = "read_skill"
SHOW_FIXTURE_TOOL_NAME = "show_fixture"
COMPUTER_TOOL_NAME = "computer"
LEARNING_MODES = ("strict", "legacy")
DEFAULT_LEARNING_MODE = "legacy"
ARCHITECTURE_MODES = ("full", "simplified")
DEFAULT_ARCHITECTURE_MODE = "full"
DEFAULT_TRANSFER_RETRIEVAL_MAX_RESULTS = DEFAULT_TRANSFER_MAX_RESULTS
DEFAULT_TRANSFER_RETRIEVAL_SCORE_WEIGHT = DEFAULT_TRANSFER_SCORE_COEFFICIENT
DEFAULT_RUNTIME_CANDIDATE_POLICY = CANDIDATE_POLICY_ANCHORED
DEFAULT_BENCHMARK_DETERMINISTIC = False
DEFAULT_BENCHMARK_PROMOTED_ONLY = False
DEFAULT_BENCHMARK_PLACEBO = False
DEFAULT_DOC_MODE = "none"
DEFAULT_DOC_RETRIEVAL_MODE = "off"
DEFAULT_DOC_BUDGET_TOKENS = 1200
DEFAULT_CONTRACT_GAP_RETRY = True
DEFAULT_CONTRACT_GAP_RETRY_STEPS = 1
DEFAULT_CONTRACT_GAP_DETERMINISTIC_RECIPES = True
DEFAULT_STRUCTURED_LESSONS_REQUIRED = True
DEFAULT_WATCHDOG_ALLOW_POSTTASK_IN_SAFE_MODE = False
DEFAULT_VERIFIER_STACK_ENABLED = False
DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.65
DEFAULT_CLARIFY_ON_LOW_CONFIDENCE = True
DEFAULT_MAX_LOW_CONFIDENCE_PROBES = 4
DEFAULT_SELF_EDIT_MODE = False
REFLECTION_ERROR_THRESHOLD = 2
MAX_VALIDATION_RETRIES_PER_STEP = 2
MAX_NO_TOOL_RECOVERY_PROMPTS = 3
DEPENDENCY_SETUP_REPEAT_THRESHOLD = 2
HOTFIX_TRANSFER_TASK_IDS: frozenset[str] = frozenset(
    {
        "shell_git_transfer_hotfix",
        "shell_git_transfer_hotfix_hard",
    }
)

DEPENDENCY_SETUP_TAGS: frozenset[str] = frozenset(
    {
        "command_not_found",
        "network",
        "not_found",
        "permission",
        "resource",
    }
)

DEPENDENCY_SETUP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bmodule\s+not\s+found\b", re.IGNORECASE),
    re.compile(r"\bno\s+module\s+named\b", re.IGNORECASE),
    re.compile(r"\bimporterror\b", re.IGNORECASE),
    re.compile(r"\bmissing\s+dependency\b", re.IGNORECASE),
    re.compile(r"\bdependency\s+missing\b", re.IGNORECASE),
)


@dataclass
class CliRunResult:
    messages: list[dict[str, Any]]
    metrics: dict[str, Any]
    task_text: str
    system_prompt: str
    lessons_text: str
    tools: list[dict[str, Any]]


@dataclass(frozen=True)
class CliPromptPreview:
    """Resolved runtime prompt bundle for display/debug tooling."""

    task_text: str
    system_prompt: str
    lessons_text: str
    tools: list[dict[str, Any]]


VerificationFilePattern = _legacy_probe_helpers.VerificationFilePattern
VerificationQueryCheck = _legacy_probe_helpers.VerificationQueryCheck
VerificationSpec = _legacy_probe_helpers.VerificationSpec
DeterministicProbeResult = _legacy_probe_helpers.DeterministicProbeResult


def _load_task_text(tasks_root: Path, task_id: str) -> str:
    """Load task description from task.md file, with fallback."""
    task_md = tasks_root / task_id / "task.md"
    if task_md.exists():
        return task_md.read_text(encoding="utf-8").strip()
    return f"Task: {task_id}. Complete using available tools."


def _parse_expected_rows(raw_rows: Any, *, field_name: str, errors: list[str]) -> tuple[tuple[str, ...], ...]:
    return _legacy_probe_helpers._parse_expected_rows(
        raw_rows,
        field_name=field_name,
        errors=errors,
    )


def _load_verification_spec_from_json(path: Path) -> tuple[VerificationSpec | None, list[str]]:
    return _legacy_probe_helpers._load_verification_spec_from_json(path)


def _infer_verification_spec_from_task_text(task_text: str) -> VerificationSpec | None:
    return _legacy_probe_helpers._infer_verification_spec_from_task_text(task_text)


def _load_verification_spec(task_dir: Path, task_text: str) -> tuple[VerificationSpec | None, list[str]]:
    return _legacy_probe_helpers._load_verification_spec(task_dir, task_text)


def _event_text_lines(events: list[dict[str, Any]]) -> tuple[set[str], str]:
    return _legacy_probe_helpers._event_text_lines(events)


def _run_sqlite_query(db_path: Path, sql: str) -> tuple[list[list[str]] | None, str | None]:
    return _legacy_probe_helpers._run_sqlite_query(db_path, sql)


def _run_deterministic_probes(
    *,
    spec: VerificationSpec | None,
    events: list[dict[str, Any]],
    workspace: DomainWorkspace,
) -> DeterministicProbeResult:
    return _legacy_probe_helpers._run_deterministic_probes(
        spec=spec,
        events=events,
        workspace=workspace,
    )


def _tool_result_block(tool_use_id: str, result: ToolResult) -> dict[str, Any]:
    content: list[dict[str, str]] = []
    if result.output:
        content.append({"type": "text", "text": result.output})
    if result.error:
        content.append({"type": "text", "text": result.error})
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "is_error": result.is_error(),
        "content": content or "",
    }


def _build_reflection_prompt(
    *,
    error_text: str,
    fingerprint: str,
    reason: str,
    include_dependency_fallback: bool = False,
) -> str:
    return _runtime_misc_helpers._build_reflection_prompt(
        error_text=error_text,
        fingerprint=fingerprint,
        reason=reason,
        include_dependency_fallback=include_dependency_fallback,
    )


def _format_contract_gap_retry_prompt(
    *,
    unresolved_gaps: list[dict[str, Any]],
    deterministic_recipes: list[str] | None = None,
    injected_hints: list[str] | None = None,
    validator_evidence: list[str] | None = None,
    max_items: int = 5,
) -> str:
    return _contract_gap_guidance._format_contract_gap_retry_prompt(
        unresolved_gaps=unresolved_gaps,
        deterministic_recipes=deterministic_recipes,
        injected_hints=injected_hints,
        validator_evidence=validator_evidence,
        max_items=max_items,
    )


def _fallback_rule_for_gap(gap: dict[str, Any]) -> str:
    return _contract_gap_guidance._fallback_rule_for_gap(gap)


def _adapter_deterministic_gap_fix_recipes(
    *,
    adapter: DomainAdapter | None,
    task_id: str,
    unresolved_gaps: list[dict[str, Any]],
    max_items: int,
) -> list[str]:
    return _contract_gap_guidance._adapter_deterministic_gap_fix_recipes(
        adapter=adapter,
        task_id=task_id,
        unresolved_gaps=unresolved_gaps,
        max_items=max_items,
    )


def _deterministic_gap_fix_recipes(
    *,
    adapter: DomainAdapter | None,
    domain: str,
    task_id: str,
    unresolved_gaps: list[dict[str, Any]],
    max_items: int = 3,
) -> list[str]:
    return _contract_gap_guidance._deterministic_gap_fix_recipes(
        adapter=adapter,
        domain=domain,
        task_id=task_id,
        unresolved_gaps=unresolved_gaps,
        max_items=max_items,
    )


def _extract_verification_lines(task_text: str, *, max_lines: int = 6) -> list[str]:
    return _verification_runtime_helpers._extract_verification_lines(
        task_text,
        max_lines=max_lines,
    )


def _dedupe_nonempty_text_rows(values: list[str]) -> list[str]:
    return _verification_runtime_helpers._dedupe_nonempty_text_rows(values)


def _extract_required_files_from_task_text(task_text: str, *, max_files: int = 8) -> list[str]:
    return _verification_runtime_helpers._extract_required_files_from_task_text(
        task_text,
        max_files=max_files,
    )


def _extract_required_file_content_patterns_from_task_text(
    task_text: str,
    *,
    max_keys_per_file: int = 12,
) -> list[dict[str, Any]]:
    return _verification_runtime_helpers._extract_required_file_content_patterns_from_task_text(
        task_text,
        max_keys_per_file=max_keys_per_file,
    )


def _normalize_required_file_content_patterns(raw: Any) -> list[dict[str, Any]]:
    return _verification_runtime_helpers._normalize_required_file_content_patterns(raw)


def _normalize_required_queries(raw: Any) -> list[dict[str, Any]]:
    return _verification_runtime_helpers._normalize_required_queries(raw)


def _load_verification_spec(
    *,
    tasks_root: Path,
    task_id: str,
    task_text: str,
) -> dict[str, Any]:
    return _verification_runtime_helpers._load_verification_spec(
        tasks_root=tasks_root,
        task_id=task_id,
        task_text=task_text,
    )


def _verification_spec_for_probe(spec: dict[str, Any] | None) -> VerificationSpec | None:
    return _legacy_probe_helpers._verification_spec_for_probe(spec)


def _run_required_files_probe(*, work_dir: Path, required_files: list[str]) -> dict[str, Any]:
    return _verification_runtime_helpers._run_required_files_probe(
        work_dir=work_dir,
        required_files=required_files,
    )


def _run_required_file_content_patterns_probe(
    *,
    work_dir: Path,
    required_file_content_patterns: list[dict[str, Any]],
) -> dict[str, Any]:
    return _verification_runtime_helpers._run_required_file_content_patterns_probe(
        work_dir=work_dir,
        required_file_content_patterns=required_file_content_patterns,
    )


def _resolve_verification_db_path(*, work_dir: Path, db_path_hint: str) -> Path:
    return _verification_runtime_helpers._resolve_verification_db_path(
        work_dir=work_dir,
        db_path_hint=db_path_hint,
    )


def _run_required_query_probe(*, db_path: Path, query_spec: dict[str, Any]) -> dict[str, Any]:
    return _verification_runtime_helpers._run_required_query_probe(
        db_path=db_path,
        query_spec=query_spec,
    )


def _collect_event_text_blobs(events: list[dict[str, Any]]) -> str:
    return _verification_runtime_helpers._collect_event_text_blobs(events)


def _is_equivalent_hotfix_git_am_command(*, command: str, patch_file: str) -> bool:
    return _hotfix_closure_helpers._is_equivalent_hotfix_git_am_command(
        command=command,
        patch_file=patch_file,
    )


def _canonicalize_hotfix_transfer_eval_events(
    *,
    events: list[dict[str, Any]],
    workspace: DomainWorkspace,
    task_id: str,
) -> list[dict[str, Any]]:
    return _hotfix_closure_helpers._canonicalize_hotfix_transfer_eval_events(
        events=events,
        workspace=workspace,
        task_id=task_id,
        is_shell_hotfix_transfer_task_fn=_is_shell_hotfix_transfer_task,
        load_hotfix_transfer_expectations_fn=_load_hotfix_transfer_expectations,
        is_equivalent_hotfix_git_am_command_fn=_is_equivalent_hotfix_git_am_command,
    )


def _normalize_expected_rows(expected_rows: Any) -> list[list[str]]:
    return _verification_runtime_helpers._normalize_expected_rows(expected_rows)


def _run_sqlite_gap_query_probe(*, db_path: Path, gap: dict[str, Any]) -> dict[str, Any]:
    return _verification_runtime_helpers._run_sqlite_gap_query_probe(
        db_path=db_path,
        gap=gap,
    )


def _build_low_confidence_clarifying_question(
    *,
    task_id: str,
    missing_verification_lines: list[str],
    unresolved_gaps: list[dict[str, Any]],
) -> str:
    return _contract_gap_guidance._build_low_confidence_clarifying_question(
        task_id=task_id,
        missing_verification_lines=missing_verification_lines,
        unresolved_gaps=unresolved_gaps,
    )


def _build_sqlite_validator_guidance_from_contract(
    *,
    contract: dict[str, Any],
    max_queries: int = 4,
) -> str:
    return _contract_gap_guidance._build_sqlite_validator_guidance_from_contract(
        contract=contract,
        max_queries=max_queries,
    )


def _contract_pattern_to_hint_text(pattern: str, *, max_chars: int = 140) -> str:
    return _contract_gap_guidance._contract_pattern_to_hint_text(
        pattern,
        max_chars=max_chars,
    )


def _build_contract_execution_guidance_from_contract(
    *,
    contract: dict[str, Any],
    max_required: int = 4,
    max_forbidden: int = 2,
) -> str:
    return _contract_gap_guidance._build_contract_execution_guidance_from_contract(
        contract=contract,
        max_required=max_required,
        max_forbidden=max_forbidden,
    )


def _build_gap_row(*, reason_code: str, gap_type: str, detail: str) -> dict[str, Any]:
    return _contract_gap_guidance._build_gap_row(
        reason_code=reason_code,
        gap_type=gap_type,
        detail=detail,
    )


def _is_shell_hotfix_transfer_task(task_id: str) -> bool:
    return str(task_id).strip() in HOTFIX_TRANSFER_TASK_IDS


def _load_hotfix_transfer_expectations(*, workspace: DomainWorkspace, task_id: str) -> dict[str, Any]:
    return _hotfix_closure_helpers._load_hotfix_transfer_expectations(
        workspace=workspace,
        task_id=task_id,
    )


def _run_shell_hotfix_transfer_closure_check(*, workspace: DomainWorkspace, task_id: str) -> dict[str, Any]:
    return _hotfix_closure_helpers._run_shell_hotfix_transfer_closure_check(
        workspace=workspace,
        task_id=task_id,
        is_shell_hotfix_transfer_task_fn=_is_shell_hotfix_transfer_task,
        load_hotfix_transfer_expectations_fn=_load_hotfix_transfer_expectations,
        build_gap_row_fn=_build_gap_row,
    )


def _is_dependency_or_setup_failure(*, error_text: str, error_tags: list[str]) -> bool:
    return _runtime_misc_helpers._is_dependency_or_setup_failure(
        error_text=error_text,
        error_tags=error_tags,
        dependency_setup_tags=DEPENDENCY_SETUP_TAGS,
        dependency_setup_patterns=DEPENDENCY_SETUP_PATTERNS,
    )


def _clip_text(text: str, *, max_chars: int = 4000) -> str:
    return clip_text(text, max_chars=max_chars)


def _normalize_llm_backend(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"openai", "openai_agents_sdk"}:
        return normalized
    return normalize_llm_backend(normalized)


def _hash_base64_png(image_b64: str | None) -> str | None:
    return _runtime_misc_helpers._hash_base64_png(image_b64)


def _normalize_coordinate(coord: Any) -> tuple[int, int] | None:
    return _runtime_misc_helpers._normalize_coordinate(coord)


def _normalize_region(region: Any) -> tuple[int, int, int, int] | None:
    return _runtime_misc_helpers._normalize_region(region)


def _extract_computer_use_metadata(tool_input: Any, result: Any) -> dict[str, Any]:
    return _runtime_misc_helpers._extract_computer_use_metadata(
        tool_input,
        result,
        normalize_coordinate_func=_normalize_coordinate,
        normalize_region_func=_normalize_region,
        hash_base64_png_func=_hash_base64_png,
    )


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _sum_rejection_counts(rejection_counts: Any) -> int:
    if not isinstance(rejection_counts, dict):
        return 0
    total = 0
    for value in rejection_counts.values():
        try:
            total += max(0, int(value or 0))
        except (TypeError, ValueError):
            continue
    return total


def _tier_from_model(model_name: str) -> str:
    return _agent_policy_helpers._tier_from_model(model_name)


def _model_from_tier(tier: str, *, base_model: str) -> str:
    return _agent_policy_helpers._model_from_tier(
        tier,
        base_model=base_model,
        sonnet_model=SONNET_MODEL,
        opus_model=OPUS_MODEL,
    )


def _load_escalation_state(*, base_model: str) -> dict[str, Any]:
    return _agent_policy_helpers._load_escalation_state(
        learning_root=LEARNING_ROOT,
        escalation_state_path=ESCALATION_STATE_PATH,
        base_model=base_model,
    )


def _save_escalation_state(state: dict[str, Any]) -> None:
    _agent_policy_helpers._save_escalation_state(
        learning_root=LEARNING_ROOT,
        escalation_state_path=ESCALATION_STATE_PATH,
        state=state,
    )


def _resolve_critic_model_for_run(
    *,
    base_model: str,
    auto_escalate: bool,
    state: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    return _agent_policy_helpers._resolve_critic_model_for_run(
        base_model=base_model,
        auto_escalate=auto_escalate,
        state=state,
        sonnet_model=SONNET_MODEL,
        opus_model=OPUS_MODEL,
    )


def _escalate_if_needed(
    *,
    state: dict[str, Any],
    base_model: str,
    auto_escalate: bool,
    eval_score: float,
    eval_passed: bool,
    critic_no_updates: bool,
    score_threshold: float,
    consecutive_runs: int,
) -> dict[str, Any]:
    return _agent_policy_helpers._escalate_if_needed(
        state=state,
        base_model=base_model,
        auto_escalate=auto_escalate,
        eval_score=eval_score,
        eval_passed=eval_passed,
        critic_no_updates=critic_no_updates,
        score_threshold=score_threshold,
        consecutive_runs=consecutive_runs,
    )


def _build_system_prompt(
    *,
    task_id: str,
    skills_text: str,
    lessons_text: str,
    domain_fragment: str,
    executor_prompt_mode: str = DEFAULT_EXECUTOR_PROMPT_MODE,
) -> str:
    return build_executor_system_prompt(
        task_id=task_id,
        skills_text=skills_text,
        lessons_text=lessons_text,
        domain_fragment=domain_fragment,
        executor_prompt_mode=executor_prompt_mode,
    )


def _normalize_executor_prompt_mode(mode: str | None) -> str:
    return normalize_executor_prompt_mode(mode)


def _placebo_hint_for_lesson(*, lesson_id: str, task_id: str, domain: str) -> str:
    return _lesson_selection_policy._placebo_hint_for_lesson(
        lesson_id=lesson_id,
        task_id=task_id,
        domain=domain,
    )


def _format_v2_lesson_block(
    matches: list[Any],
    *,
    use_placebo: bool = False,
    task_id: str = "",
    domain: str = "",
) -> tuple[str, list[str]]:
    return _lesson_selection_policy._format_v2_lesson_block(
        matches=matches,
        use_placebo=use_placebo,
        task_id=task_id,
        domain=domain,
    )


def _render_runtime_lesson_hint(
    *,
    lesson: Any,
    use_placebo: bool = False,
    task_id: str = "",
    domain: str = "",
) -> tuple[str, str, str]:
    return _lesson_selection_policy._render_runtime_lesson_hint(
        lesson=lesson,
        use_placebo=use_placebo,
        task_id=task_id,
        domain=domain,
    )


def _serialize_prerun_v2_matches(matches: list[Any]) -> list[dict[str, Any]]:
    return _lesson_selection_policy._serialize_prerun_v2_matches(matches)


def _format_legacy_placebo_lesson_block(
    *,
    lessons: list[Any],
    lessons_loaded: int,
    task_id: str,
    domain: str,
) -> str:
    return _lesson_selection_policy._format_legacy_placebo_lesson_block(
        lessons=lessons,
        lessons_loaded=lessons_loaded,
        task_id=task_id,
        domain=domain,
    )


def _has_promoted_v2_lesson_for_task(*, path: Path, task_id: str, domain: str) -> bool:
    return _lesson_selection_policy._has_promoted_v2_lesson_for_task(
        path=path,
        task_id=task_id,
        domain=domain,
    )


def _select_high_signal_prerun_matches(
    *,
    matches: list[Any],
    task_id: str,
    domain: str,
    max_results: int = 4,
    min_score: float = 0.55,
) -> list[Any]:
    return _lesson_selection_policy._select_high_signal_prerun_matches(
        matches=matches,
        task_id=task_id,
        domain=domain,
        max_results=max_results,
        min_score=min_score,
    )


def _gap_family_key_from_row(gap_row: dict[str, Any]) -> str:
    return _lesson_selection_policy._gap_family_key_from_row(gap_row)


def _gap_family_key_from_lesson(lesson: Any) -> str:
    return _lesson_selection_policy._gap_family_key_from_lesson(lesson)


def _adaptive_gap_lesson_cap(
    *,
    unresolved_gaps: list[dict[str, Any]],
    min_cap: int = 1,
    max_cap: int = 3,
) -> int:
    return _lesson_selection_policy._adaptive_gap_lesson_cap(
        unresolved_gaps=unresolved_gaps,
        min_cap=min_cap,
        max_cap=max_cap,
    )


def _select_gap_targeted_matches(
    *,
    matches: list[Any],
    unresolved_gaps: list[dict[str, Any]],
    max_lessons: int,
    min_score: float = 0.25,
) -> list[Any]:
    return _lesson_selection_policy._select_gap_targeted_matches(
        matches=matches,
        unresolved_gaps=unresolved_gaps,
        max_lessons=max_lessons,
        min_score=min_score,
    )


def _load_recent_eval_scores(
    *,
    sessions_root: Path,
    task_id: str,
    domain: str,
    limit: int = 6,
) -> list[float]:
    return _agent_policy_helpers._load_recent_eval_scores(
        sessions_root=sessions_root,
        task_id=task_id,
        domain=domain,
        limit=limit,
    )


def _load_skill_snapshots(
    *,
    entries: list[SkillManifestEntry],
    routed_refs: list[str],
) -> tuple[list[str], dict[str, str]]:
    snapshots: list[str] = []
    digests: dict[str, str] = {}
    for ref in routed_refs[:3]:
        content, err = resolve_skill_content(entries, ref)
        if err or content is None:
            continue
        digest = skill_digest(content)
        digests[ref] = digest
        snapshots.append(f"skill_ref: {ref}\nskill_digest: {digest}\n{content}")
    return snapshots, digests


def _prioritize_domain_routed_entries(
    *,
    entries: list[SkillManifestEntry],
    domain: str,
) -> list[SkillManifestEntry]:
    domain_prefix = f"{domain}/"
    return sorted(
        entries,
        key=lambda entry: (0 if entry.skill_ref.startswith(domain_prefix) else 1),
    )


def _required_skill_refs_for_domain(
    *,
    routed_refs: list[str],
    domain: str,
    require_skill_read: bool,
    task_id: str,
) -> set[str]:
    return _agent_policy_helpers._required_skill_refs_for_domain(
        routed_refs=routed_refs,
        domain=domain,
        require_skill_read=require_skill_read,
        task_id=task_id,
    )


def _is_skill_gate_satisfied(
    *,
    read_skill_refs: set[str],
    required_skill_refs: set[str],
) -> bool:
    if not required_skill_refs:
        return True
    return bool(read_skill_refs & required_skill_refs)


def _resolve_adapter(domain: str, *, cryptic_errors: bool = False, semi_helpful_errors: bool = False) -> DomainAdapter:
    return resolve_adapter(
        domain,
        cryptic_errors=cryptic_errors,
        semi_helpful_errors=semi_helpful_errors,
    )


def _resolve_adapter_with_mode(
    domain: str,
    *,
    cryptic_errors: bool,
    semi_helpful_errors: bool,
    mixed_errors: bool,
) -> DomainAdapter:
    return resolve_adapter_with_mode(
        domain,
        cryptic_errors=cryptic_errors,
        semi_helpful_errors=semi_helpful_errors,
        mixed_errors=mixed_errors,
    )


def _serialize_lesson(lesson: Any) -> dict[str, Any]:
    return {
        "category": getattr(lesson, "category", ""),
        "lesson": getattr(lesson, "lesson", ""),
        "evidence_steps": getattr(lesson, "evidence_steps", []),
        "eval_score": getattr(lesson, "eval_score", 0.0),
        "eval_passed": getattr(lesson, "eval_passed", False),
        "trigger_gap_signature": getattr(lesson, "trigger_gap_signature", ""),
        "action_template": getattr(lesson, "action_template", ""),
        "expected_evidence": getattr(lesson, "expected_evidence", ""),
        "reason_code": getattr(lesson, "reason_code", ""),
        "gap_type": getattr(lesson, "gap_type", ""),
    }


def _clone_json(value: Any) -> Any:
    """Best-effort deep clone that stays JSON-serializable for artifacts."""
    try:
        return json.loads(json.dumps(value, ensure_ascii=True))
    except Exception:
        return {"unserializable": str(value)}


def _build_critic_context_query(
    *,
    task_text: str,
    eval_result: dict[str, Any],
    events_tail: list[dict[str, Any]],
) -> str:
    return _agent_policy_helpers._build_critic_context_query(
        task_text=task_text,
        eval_result=eval_result,
        events_tail=events_tail,
    )


def _format_critic_context(chunks: list[Any]) -> str:
    return _agent_policy_helpers._format_critic_context(chunks)


def _normalize_learning_mode(learning_mode: str) -> str:
    mode = str(learning_mode).strip().lower()
    if mode not in LEARNING_MODES:
        allowed = ", ".join(LEARNING_MODES)
        raise ValueError(f"Unknown learning mode: {learning_mode!r}. Allowed: {allowed}")
    return mode


def _normalize_architecture_mode(architecture_mode: str) -> str:
    mode = str(architecture_mode).strip().lower()
    if mode not in ARCHITECTURE_MODES:
        allowed = ", ".join(ARCHITECTURE_MODES)
        raise ValueError(f"Unknown architecture mode: {architecture_mode!r}. Allowed: {allowed}")
    return mode


def _resolve_transfer_retrieval_policy(
    *,
    enable_transfer_retrieval: bool,
    transfer_retrieval_max_results: int,
    transfer_retrieval_score_weight: float,
) -> str:
    return _agent_policy_helpers._resolve_transfer_retrieval_policy(
        enable_transfer_retrieval=enable_transfer_retrieval,
        transfer_retrieval_max_results=transfer_retrieval_max_results,
        transfer_retrieval_score_weight=transfer_retrieval_score_weight,
        transfer_policy_always=TRANSFER_POLICY_ALWAYS,
        transfer_policy_off=TRANSFER_POLICY_OFF,
        transfer_policy_auto=TRANSFER_POLICY_AUTO,
    )

def prepare_cli_prompt_preview(*args: Any, **kwargs: Any) -> CliPromptPreview:
    from tracks.cli_sqlite.agent_runtime_loop import prepare_cli_prompt_preview as _prepare_cli_prompt_preview

    return _prepare_cli_prompt_preview(*args, **kwargs)

def run_cli_agent(*args: Any, **kwargs: Any) -> CliRunResult:
    from tracks.cli_sqlite.agent_runtime_loop import run_cli_agent as _run_cli_agent

    return _run_cli_agent(*args, **kwargs)

def _run_cli_agent_impl(*args: Any, **kwargs: Any) -> CliRunResult:
    from tracks.cli_sqlite.agent_runtime_loop import _run_cli_agent_impl as _runtime_run_cli_agent_impl

    return _runtime_run_cli_agent_impl(*args, **kwargs)
