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


@dataclass(frozen=True)
class VerificationFilePattern:
    """Deterministic file-content probe declared in VERIFICATION.json."""

    path: str
    pattern: str


@dataclass(frozen=True)
class VerificationQueryCheck:
    """Deterministic sqlite query probe declared in VERIFICATION.json."""

    id: str
    sql: str
    expected_rows: tuple[tuple[str, ...], ...]
    db_path: str = "task.db"


@dataclass(frozen=True)
class VerificationSpec:
    """Task-local deterministic probes for no-contract domains."""

    source: str
    exact_output_lines: tuple[str, ...] = ()
    required_files: tuple[str, ...] = ()
    file_content_patterns: tuple[VerificationFilePattern, ...] = ()
    query_checks: tuple[VerificationQueryCheck, ...] = ()

    def check_count(self) -> int:
        return (
            len(self.exact_output_lines)
            + len(self.required_files)
            + len(self.file_content_patterns)
            + len(self.query_checks)
        )


@dataclass(frozen=True)
class DeterministicProbeResult:
    """Unified probe result shape used for metrics + eval decisions."""

    source: str
    applicable: bool
    passed: bool
    score: float
    reasons: list[str]
    evidence: dict[str, Any]

    def to_eval_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "applicable": self.applicable,
            "passed": self.passed,
            "score": self.score,
            "reasons": list(self.reasons),
            "evidence": dict(self.evidence),
        }


def _load_task_text(tasks_root: Path, task_id: str) -> str:
    """Load task description from task.md file, with fallback."""
    task_md = tasks_root / task_id / "task.md"
    if task_md.exists():
        return task_md.read_text(encoding="utf-8").strip()
    return f"Task: {task_id}. Complete using available tools."


def _parse_expected_rows(raw_rows: Any, *, field_name: str, errors: list[str]) -> tuple[tuple[str, ...], ...]:
    if not isinstance(raw_rows, list):
        errors.append(f"{field_name}_must_be_list")
        return ()
    normalized: list[tuple[str, ...]] = []
    for row_idx, row in enumerate(raw_rows):
        if not isinstance(row, list):
            errors.append(f"{field_name}[{row_idx}]_must_be_list")
            continue
        normalized.append(tuple(str(col) for col in row))
    return tuple(normalized)


def _load_verification_spec_from_json(path: Path) -> tuple[VerificationSpec | None, list[str]]:
    """Load and schema-check VERIFICATION.json for deterministic no-contract probes."""
    errors: list[str] = []
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, [f"invalid_json:{type(exc).__name__}"]
    if not isinstance(parsed, dict):
        return None, ["root_must_be_object"]

    def read_str_list(key: str) -> tuple[str, ...]:
        raw = parsed.get(key, [])
        if raw is None:
            return ()
        if not isinstance(raw, list):
            errors.append(f"{key}_must_be_list")
            return ()
        values: list[str] = []
        for idx, item in enumerate(raw):
            text = str(item).strip() if isinstance(item, str) else ""
            if not text:
                errors.append(f"{key}[{idx}]_must_be_non_empty_string")
                continue
            values.append(text)
        return tuple(values)

    exact_output_lines = read_str_list("exact_output_lines")
    required_files = read_str_list("required_files")

    raw_patterns = parsed.get("file_content_patterns", [])
    file_content_patterns: list[VerificationFilePattern] = []
    if raw_patterns is not None:
        if not isinstance(raw_patterns, list):
            errors.append("file_content_patterns_must_be_list")
        else:
            for idx, row in enumerate(raw_patterns):
                if not isinstance(row, dict):
                    errors.append(f"file_content_patterns[{idx}]_must_be_object")
                    continue
                path_value = str(row.get("path", "")).strip()
                pattern_value = str(row.get("pattern", "")).strip()
                if not path_value:
                    errors.append(f"file_content_patterns[{idx}].path_required")
                    continue
                if not pattern_value:
                    errors.append(f"file_content_patterns[{idx}].pattern_required")
                    continue
                file_content_patterns.append(
                    VerificationFilePattern(path=path_value, pattern=pattern_value)
                )

    raw_queries = parsed.get("query_checks", [])
    query_checks: list[VerificationQueryCheck] = []
    if raw_queries is not None:
        if not isinstance(raw_queries, list):
            errors.append("query_checks_must_be_list")
        else:
            for idx, row in enumerate(raw_queries):
                if not isinstance(row, dict):
                    errors.append(f"query_checks[{idx}]_must_be_object")
                    continue
                query_sql = str(row.get("sql", "")).strip()
                if not query_sql:
                    errors.append(f"query_checks[{idx}].sql_required")
                    continue
                query_id = str(row.get("id", f"query_{idx}")).strip() or f"query_{idx}"
                db_path = str(row.get("db_path", "task.db")).strip() or "task.db"
                expected_rows = _parse_expected_rows(
                    row.get("expected_rows", []),
                    field_name=f"query_checks[{idx}].expected_rows",
                    errors=errors,
                )
                query_checks.append(
                    VerificationQueryCheck(
                        id=query_id,
                        sql=query_sql,
                        expected_rows=expected_rows,
                        db_path=db_path,
                    )
                )

    if errors:
        return None, errors

    spec = VerificationSpec(
        source="VERIFICATION.json",
        exact_output_lines=exact_output_lines,
        required_files=required_files,
        file_content_patterns=tuple(file_content_patterns),
        query_checks=tuple(query_checks),
    )
    if spec.check_count() == 0:
        return None, ["empty_spec"]
    return spec, []


def _infer_verification_spec_from_task_text(task_text: str) -> VerificationSpec | None:
    """Fallback parser for task.md when no explicit VERIFICATION.json is present."""
    lines = task_text.splitlines()

    exact_output_lines: list[str] = []
    if re.search(r"\bprint\s+exactly\b", task_text, flags=re.IGNORECASE):
        for line in lines:
            match = re.match(r"^\s*[-*]\s*`([^`]+)`\s*$", line.strip())
            if match:
                exact_output_lines.append(match.group(1).strip())

    required_files: list[str] = []
    required_files.extend(
        re.findall(
            r"(?i)\bcreate\b[^`\n]*\bnamed\s+`([^`]+)`",
            task_text,
        )
    )
    required_files.extend(
        re.findall(
            r"(?i)\bwrite\b[^`\n]*`([^`]+)`",
            task_text,
        )
    )
    unique_required_files = tuple(dict.fromkeys(name.strip() for name in required_files if name.strip()))

    spec = VerificationSpec(
        source="task.md",
        exact_output_lines=tuple(dict.fromkeys(text for text in exact_output_lines if text)),
        required_files=unique_required_files,
    )
    if spec.check_count() == 0:
        return None
    return spec


def _load_verification_spec(task_dir: Path, task_text: str) -> tuple[VerificationSpec | None, list[str]]:
    spec_path = task_dir / "VERIFICATION.json"
    if spec_path.exists():
        return _load_verification_spec_from_json(spec_path)
    return _infer_verification_spec_from_task_text(task_text), []


def _event_text_lines(events: list[dict[str, Any]]) -> tuple[set[str], str]:
    """Extract normalized event output lines so exact-line probes stay deterministic."""
    raw_fragments: list[str] = []
    normalized_lines: set[str] = set()
    for row in events:
        if not isinstance(row, dict):
            continue
        for key in ("output", "error"):
            value = row.get(key)
            if not isinstance(value, str) or not value.strip():
                continue
            raw_fragments.append(value)
            for line in value.splitlines():
                stripped = line.strip()
                if stripped:
                    normalized_lines.add(stripped)
            try:
                payload = json.loads(value)
            except Exception:
                continue
            if isinstance(payload, dict):
                stdout = payload.get("stdout")
                if isinstance(stdout, str):
                    for line in stdout.splitlines():
                        stripped = line.strip()
                        if stripped:
                            normalized_lines.add(stripped)
    return normalized_lines, "\n".join(raw_fragments)


def _run_sqlite_query(db_path: Path, sql: str) -> tuple[list[list[str]] | None, str | None]:
    try:
        with sqlite3.connect(str(db_path)) as conn:
            rows = conn.execute(sql).fetchall()
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
    return [[str(col) for col in row] for row in rows], None


def _run_deterministic_probes(
    *,
    spec: VerificationSpec | None,
    events: list[dict[str, Any]],
    workspace: DomainWorkspace,
) -> DeterministicProbeResult:
    if spec is None or spec.check_count() <= 0:
        return DeterministicProbeResult(
            source="none",
            applicable=False,
            passed=False,
            score=0.0,
            reasons=["no_verification_spec"],
            evidence={},
        )

    checks_total = 0
    checks_passed = 0
    reasons: list[str] = []
    evidence: dict[str, Any] = {}
    output_lines, output_blob = _event_text_lines(events)

    if spec.exact_output_lines:
        checks_total += len(spec.exact_output_lines)
        matched: list[str] = []
        missing: list[str] = []
        for expected in spec.exact_output_lines:
            if expected in output_lines:
                checks_passed += 1
                matched.append(expected)
            else:
                missing.append(expected)
                reasons.append("missing_exact_output_line")
        evidence["exact_output_lines"] = {"matched": matched, "missing": missing}

    if spec.required_files:
        checks_total += len(spec.required_files)
        missing_files: list[str] = []
        for rel_path in spec.required_files:
            if (workspace.work_dir / rel_path).exists():
                checks_passed += 1
            else:
                missing_files.append(rel_path)
                reasons.append("missing_required_file")
        evidence["required_files"] = {"missing": missing_files}

    if spec.file_content_patterns:
        checks_total += len(spec.file_content_patterns)
        pattern_results: list[dict[str, Any]] = []
        for probe in spec.file_content_patterns:
            file_path = workspace.work_dir / probe.path
            if not file_path.exists():
                reasons.append("missing_required_file")
                pattern_results.append(
                    {"path": probe.path, "pattern": probe.pattern, "matched": False, "error": "missing_file"}
                )
                continue
            try:
                file_text = file_path.read_text(encoding="utf-8")
            except Exception as exc:
                reasons.append("file_pattern_mismatch")
                pattern_results.append(
                    {
                        "path": probe.path,
                        "pattern": probe.pattern,
                        "matched": False,
                        "error": f"{type(exc).__name__}:{exc}",
                    }
                )
                continue
            matched = bool(re.search(probe.pattern, file_text, flags=0))
            if matched:
                checks_passed += 1
            else:
                reasons.append("file_pattern_mismatch")
            pattern_results.append({"path": probe.path, "pattern": probe.pattern, "matched": matched})
        evidence["file_content_patterns"] = pattern_results

    if spec.query_checks:
        checks_total += len(spec.query_checks)
        query_results: list[dict[str, Any]] = []
        for probe in spec.query_checks:
            db_path = workspace.work_dir / probe.db_path
            actual_rows, query_error = _run_sqlite_query(db_path=db_path, sql=probe.sql)
            expected_rows = [list(row) for row in probe.expected_rows]
            matched = query_error is None and actual_rows == expected_rows
            if matched:
                checks_passed += 1
            else:
                reasons.append("query_check_mismatch" if query_error is None else "query_check_error")
            query_results.append(
                {
                    "id": probe.id,
                    "db_path": probe.db_path,
                    "sql": probe.sql,
                    "matched": matched,
                    "error": query_error,
                    "expected_rows": expected_rows,
                    "actual_rows": actual_rows,
                }
            )
        evidence["query_checks"] = query_results

    if output_blob:
        evidence["event_output_chars"] = len(output_blob)
    score = 0.0 if checks_total <= 0 else round(checks_passed / float(checks_total), 3)
    passed = checks_total > 0 and len(reasons) == 0
    return DeterministicProbeResult(
        source=spec.source,
        applicable=checks_total > 0,
        passed=passed,
        score=(1.0 if passed else score),
        reasons=sorted(set(reasons)),
        evidence=evidence,
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
    """
    Convert the runtime verifier dict into the legacy deterministic probe spec.

    Why this exists:
    - The runtime verifier stack now uses dict-based specs.
    - Existing deterministic probe evaluator expects VerificationSpec dataclass.
    - We keep a small adapter instead of forking probe logic.
    """
    if not isinstance(spec, dict):
        return None
    exact_output_lines = tuple(
        _dedupe_nonempty_text_rows([str(value) for value in (spec.get("exact_output_lines", []) or [])])
    )
    required_files = tuple(
        _dedupe_nonempty_text_rows([str(value) for value in (spec.get("required_files", []) or [])])
    )
    file_content_patterns_rows = _normalize_required_file_content_patterns(
        spec.get("required_file_content_patterns", [])
    )
    file_content_patterns: list[VerificationFilePattern] = []
    for row in file_content_patterns_rows:
        rel_path = str(row.get("path", "")).strip()
        for pattern in row.get("patterns", []):
            pattern_text = str(pattern).strip()
            if rel_path and pattern_text:
                file_content_patterns.append(
                    VerificationFilePattern(path=rel_path, pattern=pattern_text)
                )
    query_checks_rows = _normalize_required_queries(spec.get("required_queries", []))
    query_checks: list[VerificationQueryCheck] = []
    for row in query_checks_rows:
        expected_rows_raw = row.get("expected_rows", [])
        expected_rows = tuple(tuple(str(col) for col in rec) for rec in expected_rows_raw)
        db_path = str(row.get("db_path", "task.db")).strip() or "task.db"
        query_checks.append(
            VerificationQueryCheck(
                id=str(row.get("id", "")).strip() or "required_query",
                sql=str(row.get("sql", "")).strip(),
                expected_rows=expected_rows,
                db_path=db_path,
            )
        )
    probe_spec = VerificationSpec(
        source=str(spec.get("source", "")).strip() or "none",
        exact_output_lines=exact_output_lines,
        required_files=required_files,
        file_content_patterns=tuple(file_content_patterns),
        query_checks=tuple(query_checks),
    )
    if probe_spec.check_count() <= 0:
        return None
    return probe_spec


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
    """
    Detect equivalent `git am` variants for hotfix transfer contract matching.

    We intentionally allow common equivalent forms that can break strict regex
    matching in CONTRACT required_event_patterns:
    - `git -C target_repo am ../<patch>`
    - `git am --3way ../<patch>`
    - quoted patch path variants (`'../<patch>'`, `"../<patch>"`)
    """
    text = str(command or "")
    patch = str(patch_file or "").strip()
    if not text.strip() or not patch:
        return False
    if not re.search(r"(?i)\bgit\b", text) or not re.search(r"(?i)\bam\b", text):
        return False
    am_calls = re.finditer(
        r"(?is)\bgit\b(?:\s+-C\s+[^\s;&|]+)?\s+am\b(?P<tail>[^\n;&|]*)",
        text,
    )
    for match in am_calls:
        tail = str(match.group("tail") or "")
        if re.search(
            rf"(?is)(?:^|[\s\"'])(?:\./)?(?:\.\./)?{re.escape(patch)}(?:[\s\"']|$)",
            tail,
        ):
            return True
    return False


def _canonicalize_hotfix_transfer_eval_events(
    *,
    events: list[dict[str, Any]],
    workspace: DomainWorkspace,
    task_id: str,
) -> list[dict[str, Any]]:
    """
    Canonicalize hotfix transfer git-am event variants before contract matching.

    Scope is intentionally narrow and backward-compatible:
    - only applies to shell hotfix transfer task ids
    - keeps original events intact, optionally appending one synthetic alias
    - never touches persisted events on disk
    """
    if not _is_shell_hotfix_transfer_task(task_id):
        return events

    expected = _load_hotfix_transfer_expectations(workspace=workspace, task_id=task_id)
    patch_file = str(expected.get("patch_file", "")).strip()
    if not patch_file:
        return events

    canonical_command = f"git am ../{patch_file}"
    canonical_pattern = re.compile(
        rf"(?is)\bgit\s+am\s+\.\./{re.escape(patch_file)}(?:\s|$|[\"'])"
    )

    # Fast path: canonical command already present in raw events.
    for row in events:
        if not isinstance(row, dict) or str(row.get("tool", "")).strip() != "run_bash":
            continue
        tool_input = row.get("tool_input", {})
        if not isinstance(tool_input, dict):
            continue
        command = str(tool_input.get("command", "") or "")
        if canonical_pattern.search(command):
            return events

    # Append one synthetic alias event when we detect an equivalent variant.
    for row in events:
        if not isinstance(row, dict) or str(row.get("tool", "")).strip() != "run_bash":
            continue
        tool_input = row.get("tool_input", {})
        if not isinstance(tool_input, dict):
            continue
        command = str(tool_input.get("command", "") or "")
        if not _is_equivalent_hotfix_git_am_command(command=command, patch_file=patch_file):
            continue
        synthetic_event = {
            "step": row.get("step"),
            "tool": "run_bash",
            "tool_input": {"command": canonical_command},
            "ok": True,
            "output": "",
            "error": None,
        }
        return [*events, synthetic_event]
    return events


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
    """
    Resolve deterministic closure-check expectations for hotfix transfer tasks.

    For the hard task, runtime variants come from `variant_spec.json`. For the
    base task, fixed defaults are used.
    """
    expectations: dict[str, Any] = {
        "patch_file": "hotfix.patch",
        "hotfix_file": "hotfix.txt",
        "commit_message": "hotfix: add retry backoff note",
        "summary_lines": [
            "TRANSFER_BRANCH main",
            "TRANSFER_PATCHES 1",
        ],
    }
    if str(task_id).strip() != "shell_git_transfer_hotfix_hard":
        return expectations
    variant_path = workspace.work_dir / "variant_spec.json"
    if not variant_path.exists():
        return expectations
    try:
        variant_payload = json.loads(variant_path.read_text(encoding="utf-8"))
    except Exception:
        return expectations
    if not isinstance(variant_payload, dict):
        return expectations
    patch_file = str(variant_payload.get("patch_file", "")).strip()
    hotfix_file = str(variant_payload.get("hotfix_file", "")).strip()
    commit_message = str(variant_payload.get("commit_message", "")).strip()
    summary_lines = variant_payload.get("summary_lines", [])
    if patch_file:
        expectations["patch_file"] = patch_file
    if hotfix_file:
        expectations["hotfix_file"] = hotfix_file
    if commit_message:
        expectations["commit_message"] = commit_message
    if isinstance(summary_lines, list):
        clean_summary = [str(row).strip() for row in summary_lines if str(row).strip()]
        if clean_summary:
            expectations["summary_lines"] = clean_summary
    return expectations


def _run_shell_hotfix_transfer_closure_check(*, workspace: DomainWorkspace, task_id: str) -> dict[str, Any]:
    """
    Run deterministic pre-stop closure checks for shell hotfix transfer tasks.

    This validates two closure conditions before allowing stop:
    - patch actually landed in `target_repo` history
    - transfer summary file contains required lines
    """
    if not _is_shell_hotfix_transfer_task(task_id):
        return {
            "applicable": False,
            "passed": True,
            "evidence": [],
            "missing_gaps": [],
        }
    expected = _load_hotfix_transfer_expectations(workspace=workspace, task_id=task_id)
    patch_file = str(expected.get("patch_file", "")).strip()
    hotfix_file = str(expected.get("hotfix_file", "")).strip()
    commit_message = str(expected.get("commit_message", "")).strip()
    summary_lines = [str(row).strip() for row in (expected.get("summary_lines", []) or []) if str(row).strip()]
    patch_path = workspace.work_dir / patch_file
    target_repo = workspace.work_dir / "target_repo"
    hotfix_path = target_repo / hotfix_file
    summary_path = target_repo / "transfer_summary.txt"

    evidence: list[str] = [
        f"closure_check task_id={task_id}",
        f"closure_expect patch_file={patch_file}",
        f"closure_expect hotfix_file={hotfix_file}",
        f"closure_expect summary_lines={json.dumps(summary_lines, ensure_ascii=True)}",
    ]
    missing_gaps: list[dict[str, Any]] = []

    if patch_file and not patch_path.exists():
        missing_gaps.append(
            _build_gap_row(
                reason_code="missing_required_file",
                gap_type="required_file",
                detail=patch_file,
            )
        )
    if hotfix_file and not hotfix_path.exists():
        missing_gaps.append(
            _build_gap_row(
                reason_code="missing_required_file",
                gap_type="required_file",
                detail=f"target_repo/{hotfix_file}",
            )
        )

    if not summary_path.exists():
        missing_gaps.append(
            _build_gap_row(
                reason_code="missing_required_file",
                gap_type="required_file",
                detail="target_repo/transfer_summary.txt",
            )
        )
    else:
        summary_text = summary_path.read_text(encoding="utf-8", errors="replace")
        for line in summary_lines:
            if line not in summary_text:
                missing_gaps.append(
                    _build_gap_row(
                        reason_code="missing_required_file_content_pattern",
                        gap_type="required_file_content_pattern",
                        detail=f"target_repo/transfer_summary.txt::{line}",
                    )
                )

    # Ensure the target history contains the expected patch commit subject.
    # This catches "file copied manually" paths that bypass actual patch apply.
    if commit_message and target_repo.exists():
        try:
            log_result = subprocess.run(
                ["git", "-C", str(target_repo), "log", "--format=%s", "-n", "20"],
                capture_output=True,
                text=True,
                timeout=6.0,
                check=False,
            )
            if log_result.returncode != 0:
                missing_gaps.append(
                    _build_gap_row(
                        reason_code="missing_required_event_pattern",
                        gap_type="required_event_pattern",
                        detail=f"git_log_failed:{(log_result.stderr or log_result.stdout or '').strip()}",
                    )
                )
            else:
                subjects = [row.strip() for row in (log_result.stdout or "").splitlines() if row.strip()]
                if commit_message not in subjects:
                    missing_gaps.append(
                        _build_gap_row(
                            reason_code="missing_required_event_pattern",
                            gap_type="required_event_pattern",
                            detail=commit_message,
                        )
                    )
        except Exception as exc:
            missing_gaps.append(
                _build_gap_row(
                    reason_code="missing_required_event_pattern",
                    gap_type="required_event_pattern",
                    detail=f"git_log_exception:{type(exc).__name__}:{exc}",
                )
            )

    # Ensure the expected hotfix file is present in HEAD tree (committed state).
    if hotfix_file and target_repo.exists():
        show_result = subprocess.run(
            ["git", "-C", str(target_repo), "show", f"HEAD:{hotfix_file}"],
            capture_output=True,
            text=True,
            timeout=6.0,
            check=False,
        )
        if show_result.returncode != 0:
            missing_gaps.append(
                _build_gap_row(
                    reason_code="missing_required_file",
                    gap_type="required_file",
                    detail=f"target_repo/{hotfix_file}",
                )
            )

    deduped: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()
    for gap in missing_gaps:
        signature = str(gap.get("gap_signature", "")).strip()
        if not signature or signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        deduped.append(gap)
    missing_gaps = deduped
    if missing_gaps:
        evidence.extend(
            [f"closure_missing {row.get('reason_code')}::{row.get('gap_type')}::{row.get('detail')}" for row in missing_gaps]
        )
    else:
        evidence.append("closure_check passed")
    return {
        "applicable": True,
        "passed": len(missing_gaps) == 0,
        "evidence": evidence,
        "missing_gaps": missing_gaps,
        "expected": expected,
    }


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
    lowered = model_name.lower()
    if "opus" in lowered:
        return "opus"
    if "sonnet" in lowered:
        return "sonnet"
    return "haiku"


def _model_from_tier(tier: str, *, base_model: str) -> str:
    if tier == "haiku":
        return base_model
    if tier == "sonnet":
        return SONNET_MODEL
    return OPUS_MODEL


def _load_escalation_state(*, base_model: str) -> dict[str, Any]:
    LEARNING_ROOT.mkdir(parents=True, exist_ok=True)
    default = {
        "tier": _tier_from_model(base_model),
        "override_runs_remaining": 0,
        "low_score_streak": 0,
        "critic_no_updates_streak": 0,
        "last_trigger": None,
    }
    if not ESCALATION_STATE_PATH.exists():
        return default
    try:
        parsed = json.loads(ESCALATION_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return default
    if not isinstance(parsed, dict):
        return default
    merged = dict(default)
    merged.update(parsed)
    merged["tier"] = str(merged.get("tier", default["tier"])).strip() or default["tier"]
    merged["override_runs_remaining"] = max(0, int(merged.get("override_runs_remaining", 0) or 0))
    merged["low_score_streak"] = max(0, int(merged.get("low_score_streak", 0) or 0))
    merged["critic_no_updates_streak"] = max(0, int(merged.get("critic_no_updates_streak", 0) or 0))
    return merged


def _save_escalation_state(state: dict[str, Any]) -> None:
    LEARNING_ROOT.mkdir(parents=True, exist_ok=True)
    ESCALATION_STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=True), encoding="utf-8")


def _resolve_critic_model_for_run(
    *,
    base_model: str,
    auto_escalate: bool,
    state: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    if not auto_escalate:
        state["tier"] = _tier_from_model(base_model)
        state["override_runs_remaining"] = 0
        return base_model, state

    if int(state.get("override_runs_remaining", 0) or 0) <= 0:
        state["tier"] = _tier_from_model(base_model)
        state["override_runs_remaining"] = 0
        return base_model, state

    tier = str(state.get("tier", _tier_from_model(base_model)))
    state["override_runs_remaining"] = max(0, int(state.get("override_runs_remaining", 0)) - 1)
    return _model_from_tier(tier, base_model=base_model), state


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
    if eval_score < score_threshold:
        state["low_score_streak"] = max(0, int(state.get("low_score_streak", 0))) + 1
    else:
        state["low_score_streak"] = 0

    if (not eval_passed) and critic_no_updates:
        state["critic_no_updates_streak"] = max(0, int(state.get("critic_no_updates_streak", 0))) + 1
    else:
        state["critic_no_updates_streak"] = 0

    if not auto_escalate:
        return state

    low_trigger = int(state.get("low_score_streak", 0)) >= consecutive_runs
    no_update_trigger = int(state.get("critic_no_updates_streak", 0)) >= consecutive_runs
    if not (low_trigger or no_update_trigger):
        return state

    current_tier = str(state.get("tier", _tier_from_model(base_model))).strip() or _tier_from_model(base_model)
    if current_tier == "haiku":
        next_tier = "sonnet"
    else:
        next_tier = "opus"

    state["tier"] = next_tier
    state["override_runs_remaining"] = 3
    state["low_score_streak"] = 0
    state["critic_no_updates_streak"] = 0
    state["last_trigger"] = "low_score" if low_trigger else "critic_no_updates"
    return state


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
    scores: list[float] = []
    candidates = sorted(
        [path for path in sessions_root.glob("session-*/metrics.json") if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for metrics_path in candidates:
        try:
            row = json.loads(metrics_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(row, dict):
            continue
        if str(row.get("task_id", "")).strip() != task_id:
            continue
        if str(row.get("domain", "")).strip() != domain:
            continue
        try:
            score = float(row.get("eval_score", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        scores.append(score)
        if len(scores) >= limit:
            break
    return list(reversed(scores))


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
    """Gate only on active-domain skills to prevent cross-domain deadlocks."""
    if not require_skill_read:
        return set()
    domain_prefix = f"{domain}/"
    domain_refs = [ref for ref in routed_refs if ref.startswith(domain_prefix)]
    if not domain_refs:
        return set()

    # Prefer the skill whose ref directly matches task_id (underscore/hyphen tolerant).
    # This keeps near-duplicate families deterministic, e.g.:
    # incremental_reconcile vs incremental_reconcile_nano.
    normalized_task = str(task_id).strip().lower().replace("_", "-")
    if normalized_task:
        for ref in domain_refs:
            if normalized_task in ref.lower():
                return {ref}
    return {domain_refs[0]}


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
    # Query composition deliberately mixes:
    # - task intent
    # - evaluator failure reasons
    # - recent concrete runtime errors
    # so strict retrieval can pull docs that are actionable for this run.
    eval_reasons = eval_result.get("reasons", [])
    reasons_text = ", ".join(str(r) for r in eval_reasons) if isinstance(eval_reasons, list) else str(eval_reasons)
    error_snippets: list[str] = []
    for row in events_tail:
        err = row.get("error")
        if isinstance(err, str) and err.strip():
            error_snippets.append(err.strip()[:180])
    joined_errors = " | ".join(error_snippets[-6:])
    return f"task={task_text}\nreasons={reasons_text}\nerrors={joined_errors}"


def _format_critic_context(chunks: list[Any]) -> str:
    # Keep explicit source IDs in critic context so downstream analysis can
    # audit which docs the strict critic relied on.
    if not chunks:
        return ""
    lines: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        title = getattr(chunk, "source_title", "doc")
        source_id = getattr(chunk, "source_id", f"doc-{idx}")
        text = getattr(chunk, "text", "")
        lines.append(f"[{idx}] {title} ({source_id})\n{text}")
    return "\n\n".join(lines)


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
    """
    Resolve transfer retrieval policy for on-error Memory V2 injection.

    Default behavior is auto strict-first retrieval with limited transfer
    backfill. Existing dev controls remain available:
    - enable_transfer_retrieval=True forces transfer lane on
    - transfer_retrieval_max_results=0 or score_weight<=0 forces transfer off
    """
    if bool(enable_transfer_retrieval):
        return TRANSFER_POLICY_ALWAYS
    if int(transfer_retrieval_max_results) <= 0 or float(transfer_retrieval_score_weight) <= 0.0:
        return TRANSFER_POLICY_OFF
    return TRANSFER_POLICY_AUTO



def prepare_cli_prompt_preview(
    *,
    task_id: str,
    task: str | None,
    domain: str = "sqlite",
    learning_mode: str = DEFAULT_LEARNING_MODE,
    bootstrap: bool = False,
    require_skill_read: bool = True,
    opaque_tools: bool = False,
    cryptic_errors: bool = False,
    semi_helpful_errors: bool = False,
    mixed_errors: bool = False,
    documentation: list[str] | None = None,
    doc_mode: str = DEFAULT_DOC_MODE,
    doc_budget_tokens: int = DEFAULT_DOC_BUDGET_TOKENS,
    doc_retrieval: str = DEFAULT_DOC_RETRIEVAL_MODE,
    doc_retriever_model: str | None = None,
    executor_docs: bool = False,
    executor_prompt_mode: str = DEFAULT_EXECUTOR_PROMPT_MODE,
) -> CliPromptPreview:
    kwargs = locals().copy()
    from tracks.cli_sqlite.agent_runtime_loop import prepare_cli_prompt_preview as _prepare_cli_prompt_preview

    return _prepare_cli_prompt_preview(**kwargs)


def run_cli_agent(
    *,
    cfg: CortexConfig,
    task_id: str,
    task: str | None,
    session_id: int,
    max_steps: int = 12,
    model_executor: str = DEFAULT_EXECUTOR_MODEL,
    model_critic: str = DEFAULT_CRITIC_MODEL,
    model_judge: str | None = None,
    domain: str = "sqlite",
    learning_mode: str = DEFAULT_LEARNING_MODE,
    architecture_mode: str = DEFAULT_ARCHITECTURE_MODE,
    bootstrap: bool = False,
    posttask_mode: str = "candidate",
    posttask_learn: bool = True,
    memory_v2_demo_mode: bool = False,
    verbose: bool = False,
    auto_escalate_critic: bool = True,
    escalation_score_threshold: float = 0.75,
    escalation_consecutive_runs: int = 2,
    promotion_min_runs: int = 3,
    promotion_min_delta: float = 0.2,
    promotion_max_regressions: int = 1,
    require_skill_read: bool = True,
    opaque_tools: bool = False,
    cryptic_errors: bool = False,
    semi_helpful_errors: bool = False,
    mixed_errors: bool = False,
    enable_transfer_retrieval: bool = False,
    transfer_retrieval_max_results: int = DEFAULT_TRANSFER_RETRIEVAL_MAX_RESULTS,
    transfer_retrieval_score_weight: float = DEFAULT_TRANSFER_RETRIEVAL_SCORE_WEIGHT,
    documentation: list[str] | None = None,
    doc_mode: str = DEFAULT_DOC_MODE,
    doc_budget_tokens: int = DEFAULT_DOC_BUDGET_TOKENS,
    doc_retrieval: str = DEFAULT_DOC_RETRIEVAL_MODE,
    doc_retriever_model: str | None = None,
    judge_docs: bool = False,
    executor_docs: bool = False,
    executor_prompt_mode: str = DEFAULT_EXECUTOR_PROMPT_MODE,
    judge_diagnostic: bool = False,
    contract_gap_retry: bool = DEFAULT_CONTRACT_GAP_RETRY,
    contract_gap_retry_steps: int = DEFAULT_CONTRACT_GAP_RETRY_STEPS,
    contract_gap_deterministic_recipes: bool = DEFAULT_CONTRACT_GAP_DETERMINISTIC_RECIPES,
    structured_lessons_required: bool = DEFAULT_STRUCTURED_LESSONS_REQUIRED,
    verifier_stack_enabled: bool = DEFAULT_VERIFIER_STACK_ENABLED,
    low_confidence_threshold: float = DEFAULT_LOW_CONFIDENCE_THRESHOLD,
    clarify_on_low_confidence: bool = DEFAULT_CLARIFY_ON_LOW_CONFIDENCE,
    max_low_confidence_probes: int = DEFAULT_MAX_LOW_CONFIDENCE_PROBES,
    self_edit_mode: bool = DEFAULT_SELF_EDIT_MODE,
    llm_backend: str = DEFAULT_LLM_BACKEND,
    benchmark_deterministic: bool = DEFAULT_BENCHMARK_DETERMINISTIC,
    benchmark_promoted_only: bool = DEFAULT_BENCHMARK_PROMOTED_ONLY,
    benchmark_placebo: bool = DEFAULT_BENCHMARK_PLACEBO,
    watchdog_allow_posttask_in_safe_mode: bool = DEFAULT_WATCHDOG_ALLOW_POSTTASK_IN_SAFE_MODE,
    on_step: Callable[[int, str, bool, str | None], Any] | None = None,
) -> CliRunResult:
    kwargs = locals().copy()
    from tracks.cli_sqlite.agent_runtime_loop import run_cli_agent as _run_cli_agent

    return _run_cli_agent(**kwargs)


def _run_cli_agent_impl(
    *,
    cfg: CortexConfig,
    task_id: str,
    task: str | None,
    session_id: int,
    max_steps: int = 12,
    model_executor: str = DEFAULT_EXECUTOR_MODEL,
    model_critic: str = DEFAULT_CRITIC_MODEL,
    model_judge: str | None = None,
    domain: str = "sqlite",
    learning_mode: str = DEFAULT_LEARNING_MODE,
    architecture_mode: str = DEFAULT_ARCHITECTURE_MODE,
    bootstrap: bool = False,
    posttask_mode: str = "candidate",
    posttask_learn: bool = True,
    memory_v2_demo_mode: bool = False,
    verbose: bool = False,
    auto_escalate_critic: bool = True,
    escalation_score_threshold: float = 0.75,
    escalation_consecutive_runs: int = 2,
    promotion_min_runs: int = 3,
    promotion_min_delta: float = 0.2,
    promotion_max_regressions: int = 1,
    require_skill_read: bool = True,
    opaque_tools: bool = False,
    cryptic_errors: bool = False,
    semi_helpful_errors: bool = False,
    mixed_errors: bool = False,
    enable_transfer_retrieval: bool = False,
    transfer_retrieval_max_results: int = DEFAULT_TRANSFER_RETRIEVAL_MAX_RESULTS,
    transfer_retrieval_score_weight: float = DEFAULT_TRANSFER_RETRIEVAL_SCORE_WEIGHT,
    documentation: list[str] | None = None,
    doc_mode: str = DEFAULT_DOC_MODE,
    doc_budget_tokens: int = DEFAULT_DOC_BUDGET_TOKENS,
    doc_retrieval: str = DEFAULT_DOC_RETRIEVAL_MODE,
    doc_retriever_model: str | None = None,
    judge_docs: bool = False,
    executor_docs: bool = False,
    executor_prompt_mode: str = DEFAULT_EXECUTOR_PROMPT_MODE,
    judge_diagnostic: bool = False,
    contract_gap_retry: bool = DEFAULT_CONTRACT_GAP_RETRY,
    contract_gap_retry_steps: int = DEFAULT_CONTRACT_GAP_RETRY_STEPS,
    contract_gap_deterministic_recipes: bool = DEFAULT_CONTRACT_GAP_DETERMINISTIC_RECIPES,
    structured_lessons_required: bool = DEFAULT_STRUCTURED_LESSONS_REQUIRED,
    verifier_stack_enabled: bool = DEFAULT_VERIFIER_STACK_ENABLED,
    low_confidence_threshold: float = DEFAULT_LOW_CONFIDENCE_THRESHOLD,
    clarify_on_low_confidence: bool = DEFAULT_CLARIFY_ON_LOW_CONFIDENCE,
    max_low_confidence_probes: int = DEFAULT_MAX_LOW_CONFIDENCE_PROBES,
    self_edit_mode: bool = DEFAULT_SELF_EDIT_MODE,
    llm_backend: str = DEFAULT_LLM_BACKEND,
    benchmark_deterministic: bool = DEFAULT_BENCHMARK_DETERMINISTIC,
    benchmark_promoted_only: bool = DEFAULT_BENCHMARK_PROMOTED_ONLY,
    benchmark_placebo: bool = DEFAULT_BENCHMARK_PLACEBO,
    watchdog_allow_posttask_in_safe_mode: bool = DEFAULT_WATCHDOG_ALLOW_POSTTASK_IN_SAFE_MODE,
    on_step: Callable[[int, str, bool, str | None], Any] | None = None,
    run_id: str | None = None,
    run_started_at: str | None = None,
    on_lifecycle_event: Callable[[str, dict[str, Any]], None] | None = None,
) -> CliRunResult:
    kwargs = locals().copy()
    from tracks.cli_sqlite.agent_runtime_loop import _run_cli_agent_impl as _runtime_run_cli_agent_impl

    return _runtime_run_cli_agent_impl(**kwargs)
