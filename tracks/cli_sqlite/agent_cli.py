from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import anthropic

from claude_print_client import ClaudePrintClient
from claude_print_runtime import (
    DEFAULT_LLM_BACKEND,
    LLM_BACKENDS as SHARED_LLM_BACKENDS,
    assistant_blocks_from_claude_print_payload,
    build_claude_print_env,
    clip_text,
    extract_first_json_object,
    normalize_claude_print_effort,
    normalize_llm_backend,
    render_message_history_for_claude_print,
    resolve_claude_print_model,
)
from config import CortexConfig
from tracks.cli_sqlite.adapter_registry import resolve_adapter, resolve_adapter_with_mode
from tracks.cli_sqlite.domain_adapter import DomainAdapter, DomainWorkspace, ToolResult
from tracks.cli_sqlite.docs_pipeline import (
    DocumentationBundle,
    build_documentation_bundle,
    normalize_doc_mode,
    normalize_doc_retrieval_mode,
    write_doc_artifacts,
)
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
LEARNING_ROOT = TRACK_ROOT / "learning"
SESSIONS_ROOT = TRACK_ROOT / "sessions"
LESSONS_PATH = LEARNING_ROOT / "lessons.jsonl"
LESSONS_V2_PATH = LEARNING_ROOT / "lessons_v2.jsonl"
MEMORY_EVENTS_PATH = LEARNING_ROOT / "memory_events.jsonl"
QUEUE_PATH = LEARNING_ROOT / "pending_skill_patches.json"
PROMOTED_PATH = LEARNING_ROOT / "promoted_skill_patches.json"
ESCALATION_STATE_PATH = LEARNING_ROOT / "critic_escalation_state.json"

DEFAULT_EXECUTOR_MODEL = "claude-haiku-4-5"
DEFAULT_CRITIC_MODEL = "claude-haiku-4-5"
SONNET_MODEL = "claude-sonnet-4-5"
OPUS_MODEL = "claude-opus-4-6"
OPENAI_DEFAULT_MODEL = "gpt-5-nano"
LLM_BACKENDS = tuple((*SHARED_LLM_BACKENDS, "openai"))
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
DEFAULT_STRUCTURED_LESSONS_REQUIRED = True
DEFAULT_VERIFIER_STACK_ENABLED = False
DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.65
DEFAULT_CLARIFY_ON_LOW_CONFIDENCE = True
DEFAULT_MAX_LOW_CONFIDENCE_PROBES = 4
DEFAULT_SELF_EDIT_MODE = False
REFLECTION_ERROR_THRESHOLD = 2
MAX_VALIDATION_RETRIES_PER_STEP = 2
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
    """
    Create a deterministic reflection request for stuck/error-heavy runs.

    The prompt explicitly requests diagnosis + smallest correction, then
    instructs the model to continue with tool use in the same turn.
    """
    reason_line = f"Trigger: {reason}." if reason else "Trigger: error escalation."
    prompt = (
        "Reflection required before the next tool call.\n"
        f"{reason_line}\n"
        f"Last error: {error_text.strip()}\n"
        f"Fingerprint: {fingerprint}\n"
        "Explain why the failure happened and the smallest corrective change. "
        "Then proceed with the next tool call."
    )
    if not include_dependency_fallback:
        return prompt
    return (
        f"{prompt}\n"
        "Deterministic fallback check:\n"
        "- Treat this fingerprint as a repeated dependency/setup failure.\n"
        "- Do not repeat the same failing setup path.\n"
        "- Choose the smallest local alternative that avoids the missing dependency."
    )


def _format_contract_gap_retry_prompt(
    *,
    unresolved_gaps: list[dict[str, Any]],
    injected_hints: list[str] | None = None,
    validator_evidence: list[str] | None = None,
    max_items: int = 5,
) -> str:
    lines = [
        "Deterministic contract gap check found unresolved requirements.",
        "Execute one focused correction step now. Do not stop yet.",
        "Unresolved gaps:",
    ]
    for index, gap in enumerate(unresolved_gaps[:max_items], start=1):
        reason = str(gap.get("reason_code", "")).strip() or "unknown_reason"
        gap_type = str(gap.get("gap_type", "")).strip() or "unknown_gap"
        detail = str(gap.get("detail", "")).strip()
        suffix = f" detail={detail}" if detail else ""
        lines.append(f"{index}. reason_code={reason} gap_type={gap_type}{suffix}")
        if reason == "required_query_mismatch":
            query_id = str(gap.get("query_id", "")).strip()
            query_sql = str(gap.get("query_sql", "")).strip()
            expected_rows = gap.get("expected_rows", [])
            actual_rows = gap.get("actual_rows", [])
            if query_id:
                lines.append(f"   - query_id={query_id}")
            if query_sql:
                lines.append(f"   - query_sql={query_sql}")
            if isinstance(expected_rows, list):
                lines.append(f"   - expected_rows={json.dumps(expected_rows, ensure_ascii=True)}")
            if isinstance(actual_rows, list):
                lines.append(f"   - actual_rows={json.dumps(actual_rows, ensure_ascii=True)}")
            lines.append(
                "   - correction rule: align database state so query_sql output exactly matches expected_rows."
            )
        elif reason == "matched_forbidden_pattern":
            lines.append(
                "   - correction rule: do not emit any SQL matching this forbidden pattern."
            )
            lines.append(
                "   - correction rule: use non-destructive alternatives only (INSERT/UPDATE/SELECT)."
            )
        elif reason == "too_many_errors":
            lines.append(
                "   - correction rule: keep next attempt deterministic with one mutating block max, then verify via SELECT queries."
            )
            lines.append(
                "   - correction rule: if verification still fails, stop and report remaining mismatch instead of guessing."
            )
    validator_rows = [str(row).strip() for row in (validator_evidence or []) if str(row).strip()]
    if validator_rows:
        lines.append("Deterministic validator evidence:")
        for row in validator_rows[:4]:
            lines.append(f"- {row}")
    extra = [str(row).strip() for row in (injected_hints or []) if str(row).strip()]
    if extra:
        lines.append("Prior lessons matching these gaps:")
        for hint in extra[:2]:
            lines.append(f"- {hint}")
    lines.append("Return tool calls only after this message.")
    return "\n".join(lines)


def _fallback_rule_for_gap(gap: dict[str, Any]) -> str:
    reason = str(gap.get("reason_code", "")).strip() or "unknown_reason"
    gap_type = str(gap.get("gap_type", "")).strip() or "unknown_gap"
    detail = str(gap.get("detail", "")).strip()
    if reason == "required_query_mismatch":
        query_id = str(gap.get("query_id", "")).strip() or "required_query"
        query_sql = str(gap.get("query_sql", "")).strip()
        expected_rows = gap.get("expected_rows", [])
        query_suffix = f" query_sql={query_sql}" if query_sql else ""
        expected_suffix = (
            f" expected_rows={json.dumps(expected_rows, ensure_ascii=True)}"
            if isinstance(expected_rows, list)
            else ""
        )
        return (
            f"When reason_code={reason}, reconcile data so {query_id} matches exactly."
            f"{query_suffix}{expected_suffix}"
        )
    if reason == "too_many_errors":
        budget_detail = detail or "error budget exhausted"
        return (
            "When reason_code=too_many_errors, treat it as a strict error-budget breach "
            f"({budget_detail}). On next attempt use one deterministic mutating SQL block at most, "
            "then run required SELECT verification queries and stop."
        )
    if reason == "matched_forbidden_pattern":
        pattern_text = detail or str(gap.get("gap_signature", "")).strip() or "forbidden_sql_pattern"
        return (
            "When reason_code=matched_forbidden_pattern, never emit SQL matching "
            f"{pattern_text}. Use non-destructive alternatives only (INSERT/UPDATE/SELECT) "
            "and verify required queries before stop."
        )
    if detail:
        return f"When reason_code={reason}, resolve gap_type={gap_type} by fixing: {detail}."
    return f"When reason_code={reason}, resolve gap_type={gap_type} before stopping."


def _extract_verification_lines(task_text: str, *, max_lines: int = 6) -> list[str]:
    """
    Parse explicit `Print exactly ... verification line(s)` requirements from task text.

    This parser is intentionally strict and deterministic: we only extract
    backtick-wrapped bullet lines directly under the marker section.
    """
    if not str(task_text).strip():
        return []
    marker = re.compile(r"print\s+exactly\s+(?:this|these)(?:\s+\d+)?\s+verification\s+line", re.IGNORECASE)
    lines = str(task_text).splitlines()
    capture = False
    collected: list[str] = []
    for raw_line in lines:
        line = str(raw_line)
        stripped = line.strip()
        if marker.search(line):
            inline_matches = re.findall(r"`([^`]+)`", line)
            for match in inline_matches:
                value = str(match).strip()
                if value:
                    collected.append(value)
            capture = True
            continue
        if not capture:
            continue
        if stripped.startswith("Constraints:") or stripped.startswith("Goal:"):
            break
        if not stripped:
            # Keep scanning through single blank lines in case the marker uses
            # a compact markdown style with spacing before bullets.
            continue
        bullet_match = re.match(r"^\s*(?:[-*]|\d+[.)])\s+`([^`]+)`\s*$", line)
        if bullet_match:
            value = str(bullet_match.group(1)).strip()
            if value:
                collected.append(value)
            if len(collected) >= max(1, int(max_lines)):
                break
            continue
        # If capture started and we hit non-bullet prose, stop deterministically.
        if collected:
            break
    deduped: list[str] = []
    seen: set[str] = set()
    for row in collected:
        if row in seen:
            continue
        seen.add(row)
        deduped.append(row)
    return deduped[: max(1, int(max_lines))]


def _dedupe_nonempty_text_rows(values: list[str]) -> list[str]:
    """Normalize string lists while preserving deterministic order."""
    rows: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        rows.append(text)
    return rows


def _extract_required_files_from_task_text(task_text: str, *, max_files: int = 8) -> list[str]:
    """
    Infer required output files from imperative task lines.

    We intentionally keep this narrow (Create/Write/Generate/Save/Output + backticks)
    to avoid speculative checks that produce noisy verifier failures.
    """
    if not str(task_text).strip():
        return []
    files: list[str] = []
    pattern = re.compile(
        r"\b(?:create|write|generate|save|output)\s+`([^`]+)`",
        re.IGNORECASE,
    )
    for line in str(task_text).splitlines():
        for match in pattern.findall(line):
            text = str(match).strip()
            if text:
                files.append(text)
            if len(files) >= max(1, int(max_files)):
                return _dedupe_nonempty_text_rows(files)
    return _dedupe_nonempty_text_rows(files)


def _extract_required_file_content_patterns_from_task_text(
    task_text: str,
    *,
    max_keys_per_file: int = 12,
) -> list[dict[str, Any]]:
    """
    Infer file-key expectations from markdown text like:
    `Write `report_manifest.json` with exact keys: `k1`, `k2``.
    """
    if not str(task_text).strip():
        return []
    lines = str(task_text).splitlines()
    rows: list[dict[str, Any]] = []
    for idx, raw_line in enumerate(lines):
        line = str(raw_line)
        match = re.search(
            r"\bwrite\s+`([^`]+)`\s+with\s+exact\s+keys?\s*:\s*(.*)$",
            line,
            flags=re.IGNORECASE,
        )
        if not match:
            continue
        rel_path = str(match.group(1)).strip()
        if not rel_path:
            continue
        key_names: list[str] = [str(name).strip() for name in re.findall(r"`([^`]+)`", str(match.group(2)))]
        cursor = idx + 1
        while cursor < len(lines) and len(key_names) < max(1, int(max_keys_per_file)):
            candidate = str(lines[cursor]).strip()
            if not candidate:
                if key_names:
                    break
                cursor += 1
                continue
            if candidate.startswith("Constraints:") or candidate.startswith("Goal:"):
                break
            inline = [str(name).strip() for name in re.findall(r"`([^`]+)`", candidate)]
            if inline:
                key_names.extend(inline)
                cursor += 1
                continue
            if key_names:
                break
            cursor += 1
        normalized_keys = _dedupe_nonempty_text_rows(key_names)[: max(1, int(max_keys_per_file))]
        if not normalized_keys:
            continue
        patterns = [rf"\"{re.escape(key)}\"\s*:" for key in normalized_keys]
        rows.append({"path": rel_path, "patterns": patterns})
    return rows


def _normalize_required_file_content_patterns(raw: Any) -> list[dict[str, Any]]:
    """Normalize `required_file_content_patterns` from VERIFICATION.json."""
    rows: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return rows
    for item in raw:
        if not isinstance(item, dict):
            continue
        rel_path = str(item.get("path", "")).strip()
        if not rel_path:
            continue
        raw_patterns = item.get("patterns")
        if not isinstance(raw_patterns, list):
            single = str(item.get("pattern", "")).strip()
            raw_patterns = [single] if single else []
        patterns = _dedupe_nonempty_text_rows([str(value).strip() for value in raw_patterns])
        if not patterns:
            continue
        rows.append({"path": rel_path, "patterns": patterns})
    return rows


def _normalize_required_queries(raw: Any) -> list[dict[str, Any]]:
    """Normalize verifier query specs into deterministic rows."""
    rows: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return rows
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        query_sql = str(item.get("sql", "")).strip()
        if not query_sql:
            continue
        query_id = str(item.get("id", "")).strip() or f"required_query_{idx + 1}"
        expected_rows = _normalize_expected_rows(item.get("expected_rows", []))
        db_path = str(item.get("db_path", "")).strip()
        row = {
            "id": query_id,
            "sql": query_sql,
            "expected_rows": expected_rows,
        }
        if db_path:
            row["db_path"] = db_path
        rows.append(row)
    return rows


def _load_verification_spec(
    *,
    tasks_root: Path,
    task_id: str,
    task_text: str,
) -> dict[str, Any]:
    """
    Load deterministic verifier anchors from task text and optional JSON spec.

    Priority rules:
    - infer narrow anchors from `task.md` (verification lines + obvious output files)
    - if `VERIFICATION.json` exists, its explicit fields override inferred fields
    """
    inferred_lines = _extract_verification_lines(task_text)
    inferred_files = _extract_required_files_from_task_text(task_text)
    inferred_file_patterns = _extract_required_file_content_patterns_from_task_text(task_text)

    spec: dict[str, Any] = {
        "source": "task_md",
        "source_path": str(tasks_root / task_id / "task.md"),
        "exact_output_lines": inferred_lines,
        "required_files": inferred_files,
        "required_file_content_patterns": inferred_file_patterns,
        "required_queries": [],
        "db_path": "",
    }

    verification_path = tasks_root / task_id / "VERIFICATION.json"
    if not verification_path.exists():
        return spec
    try:
        payload = json.loads(verification_path.read_text(encoding="utf-8"))
    except Exception:
        spec["source"] = "VERIFICATION.json_invalid"
        return spec
    if not isinstance(payload, dict):
        spec["source"] = "VERIFICATION.json_invalid"
        return spec

    # Explicit JSON entries replace inferred values for the same field.
    if "exact_output_lines" in payload:
        spec["exact_output_lines"] = _dedupe_nonempty_text_rows(
            [str(value) for value in payload.get("exact_output_lines", [])]
            if isinstance(payload.get("exact_output_lines"), list)
            else []
        )
    if "required_files" in payload:
        spec["required_files"] = _dedupe_nonempty_text_rows(
            [str(value) for value in payload.get("required_files", [])]
            if isinstance(payload.get("required_files"), list)
            else []
        )
    if "required_file_content_patterns" in payload:
        spec["required_file_content_patterns"] = _normalize_required_file_content_patterns(
            payload.get("required_file_content_patterns")
        )
    if "required_queries" in payload:
        spec["required_queries"] = _normalize_required_queries(payload.get("required_queries"))
    db_path = str(payload.get("db_path", "")).strip()
    if db_path:
        spec["db_path"] = db_path

    spec["source"] = "VERIFICATION.json"
    spec["source_path"] = str(verification_path)
    return spec


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
    missing: list[str] = []
    present: list[str] = []
    for rel_path in required_files:
        target = work_dir / rel_path
        if target.exists():
            present.append(rel_path)
        else:
            missing.append(rel_path)
    return {
        "probe_id": "required_files",
        "applicable": bool(required_files),
        "passed": len(missing) == 0,
        "detail": "matched" if len(missing) == 0 else "missing_required_file",
        "evidence": {
            "work_dir": str(work_dir),
            "required_files": list(required_files),
            "present_files": present,
            "missing_files": missing,
        },
    }


def _run_required_file_content_patterns_probe(
    *,
    work_dir: Path,
    required_file_content_patterns: list[dict[str, Any]],
) -> dict[str, Any]:
    matched: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    for row in required_file_content_patterns:
        rel_path = str(row.get("path", "")).strip()
        patterns = row.get("patterns", [])
        if not rel_path or not isinstance(patterns, list):
            continue
        target = work_dir / rel_path
        file_text = ""
        if target.exists():
            try:
                file_text = target.read_text(encoding="utf-8", errors="replace")
            except Exception:
                file_text = ""
        for pattern in patterns:
            pattern_text = str(pattern).strip()
            if not pattern_text:
                continue
            if file_text and re.search(pattern_text, file_text, flags=0):
                matched.append({"path": rel_path, "pattern": pattern_text})
            else:
                missing.append({"path": rel_path, "pattern": pattern_text})
    return {
        "probe_id": "required_file_content_patterns",
        "applicable": bool(required_file_content_patterns),
        "passed": len(missing) == 0,
        "detail": "matched" if len(missing) == 0 else "missing_required_file_content_pattern",
        "evidence": {
            "work_dir": str(work_dir),
            "matched": matched,
            "missing": missing,
        },
    }


def _resolve_verification_db_path(*, work_dir: Path, db_path_hint: str) -> Path:
    hint = str(db_path_hint).strip()
    if not hint:
        return work_dir / "task.db"
    candidate = Path(hint)
    if candidate.is_absolute():
        return candidate
    return work_dir / candidate


def _run_required_query_probe(*, db_path: Path, query_spec: dict[str, Any]) -> dict[str, Any]:
    query_id = str(query_spec.get("id", "")).strip() or "required_query"
    query_sql = str(query_spec.get("sql", "")).strip()
    expected_rows = _normalize_expected_rows(query_spec.get("expected_rows", []))
    if not query_sql:
        return {
            "probe_id": f"required_query:{query_id}",
            "applicable": False,
            "passed": False,
            "detail": "missing_query_sql",
            "evidence": {},
        }
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.execute(query_sql)
            actual_rows = [[str(cell) for cell in row] for row in cursor.fetchall()]
    except Exception as exc:
        return {
            "probe_id": f"required_query:{query_id}",
            "applicable": True,
            "passed": False,
            "detail": "required_query_error",
            "evidence": {
                "query_id": query_id,
                "query_sql": query_sql,
                "db_path": str(db_path),
                "error": f"{type(exc).__name__}: {exc}",
            },
        }
    passed = actual_rows == expected_rows
    return {
        "probe_id": f"required_query:{query_id}",
        "applicable": True,
        "passed": bool(passed),
        "detail": "matched" if passed else "required_query_mismatch",
        "evidence": {
            "query_id": query_id,
            "query_sql": query_sql,
            "db_path": str(db_path),
            "expected_rows": expected_rows,
            "actual_rows": actual_rows,
        },
    }


def _collect_event_text_blobs(events: list[dict[str, Any]]) -> str:
    """Collect textual event outputs/errors for deterministic probe checks."""
    chunks: list[str] = []
    for row in events:
        if not isinstance(row, dict):
            continue
        output = row.get("output")
        error = row.get("error")
        if isinstance(output, str) and output.strip():
            chunks.append(output)
        if isinstance(error, str) and error.strip():
            chunks.append(error)
    return "\n".join(chunks)


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
    """Normalize expected rows into deterministic string matrix."""
    normalized: list[list[str]] = []
    if not isinstance(expected_rows, list):
        return normalized
    for row in expected_rows:
        if not isinstance(row, list):
            continue
        normalized.append([str(cell) for cell in row])
    return normalized


def _run_sqlite_gap_query_probe(*, db_path: Path, gap: dict[str, Any]) -> dict[str, Any]:
    """
    Probe unresolved sqlite required_query gaps with direct deterministic SQL.

    This avoids extra model calls and validates exact expected rows.
    """
    query_id = str(gap.get("query_id", "")).strip() or "required_query"
    query_sql = str(gap.get("query_sql", "")).strip()
    expected_rows = _normalize_expected_rows(gap.get("expected_rows", []))
    if not query_sql:
        return {
            "probe_id": f"sqlite_required_query:{query_id}",
            "applicable": False,
            "passed": False,
            "detail": "missing_query_sql",
            "evidence": {},
        }
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.execute(query_sql)
            actual = [[str(cell) for cell in row] for row in cursor.fetchall()]
    except Exception as exc:
        return {
            "probe_id": f"sqlite_required_query:{query_id}",
            "applicable": True,
            "passed": False,
            "detail": f"query_error:{type(exc).__name__}:{exc}",
            "evidence": {
                "query_id": query_id,
                "query_sql": query_sql,
            },
        }
    passed = actual == expected_rows
    return {
        "probe_id": f"sqlite_required_query:{query_id}",
        "applicable": True,
        "passed": bool(passed),
        "detail": "matched" if passed else "required_query_mismatch",
        "evidence": {
            "query_id": query_id,
            "query_sql": query_sql,
            "expected_rows": expected_rows,
            "actual_rows": actual,
        },
    }


def _build_low_confidence_clarifying_question(
    *,
    task_id: str,
    missing_verification_lines: list[str],
    unresolved_gaps: list[dict[str, Any]],
) -> str:
    """
    Build a deterministic clarification request when probes are inconclusive.

    No model generation is used here; output is template-based and stable.
    """
    if missing_verification_lines:
        quoted = ", ".join(f"`{line}`" for line in missing_verification_lines[:3])
        return (
            f"Low-confidence verification for task `{task_id}` is inconclusive. "
            f"Please confirm the exact expected verification line(s): {quoted}."
        )
    if unresolved_gaps:
        gap = unresolved_gaps[0]
        reason = str(gap.get("reason_code", "")).strip() or "unknown_reason"
        gap_type = str(gap.get("gap_type", "")).strip() or "unknown_gap"
        detail = str(gap.get("detail", "")).strip()
        detail_suffix = f" detail={detail}" if detail else ""
        return (
            f"Low-confidence verification for task `{task_id}` needs one deterministic success signal. "
            f"Current unresolved gap: reason_code={reason} gap_type={gap_type}{detail_suffix}. "
            "Please provide exact expected output (line/file/query rows)."
        )
    return (
        f"Low-confidence verification for task `{task_id}` is inconclusive. "
        "Please provide one deterministic success signal: exact stdout line, file path+content, or SQL query rows."
    )


def _build_sqlite_validator_guidance_from_contract(
    *,
    contract: dict[str, Any],
    max_queries: int = 4,
) -> str:
    """
    Render deterministic validator steps from CONTRACT required queries.

    This keeps validation protocol machine-driven (contract source of truth)
    instead of relying on ad-hoc prompt prose per task.
    """
    if not isinstance(contract, dict):
        return ""
    signals = contract.get("signals", {})
    if not isinstance(signals, dict):
        return ""
    required_queries = signals.get("required_queries", [])
    if not isinstance(required_queries, list) or not required_queries:
        return ""
    lines = [
        "Deterministic validator protocol (from CONTRACT):",
        "- Before final stop, run these validator queries with run_sqlite and verify expected rows exactly.",
    ]
    added = 0
    for row in required_queries:
        if not isinstance(row, dict):
            continue
        query_id = str(row.get("id", "")).strip() or f"query_{added + 1}"
        query_sql = str(row.get("sql", "")).strip()
        expected_rows = row.get("expected_rows", [])
        if not query_sql:
            continue
        lines.append(f"- validator[{query_id}] sql={query_sql}")
        if isinstance(expected_rows, list):
            lines.append(f"  expected_rows={json.dumps(expected_rows, ensure_ascii=True)}")
        added += 1
        if added >= max(1, int(max_queries)):
            break
    if added <= 0:
        return ""
    lines.append("- If any validator mismatches, correct data and rerun validators before stopping.")
    return "\n".join(lines)


def _build_gap_row(*, reason_code: str, gap_type: str, detail: str) -> dict[str, Any]:
    text = str(detail).strip()
    return {
        "reason_code": reason_code,
        "gap_type": gap_type,
        "detail": text,
        "gap_signature": f"{reason_code}|{gap_type}|{text}",
    }


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
    tags = {str(tag).strip().lower() for tag in error_tags if str(tag).strip()}
    if tags & DEPENDENCY_SETUP_TAGS:
        return True
    lowered = str(error_text or "").strip().lower()
    return any(pattern.search(lowered) for pattern in DEPENDENCY_SETUP_PATTERNS)


def _clip_text(text: str, *, max_chars: int = 4000) -> str:
    return clip_text(text, max_chars=max_chars)


def _normalize_llm_backend(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "openai":
        return normalized
    return normalize_llm_backend(normalized)


def _extract_system_prompt_text(system: Any) -> str:
    if isinstance(system, str):
        return system.strip()
    if isinstance(system, list):
        parts: list[str] = []
        for block in system:
            if not isinstance(block, dict):
                continue
            if str(block.get("type", "")).strip().lower() != "text":
                continue
            text = str(block.get("text", "")).strip()
            if text:
                parts.append(text)
        return "\n\n".join(parts).strip()
    return str(system or "").strip()


def _tool_result_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return str(content or "").strip()
    parts: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = str(part.get("type", "")).strip().lower()
        if part_type == "text":
            text = str(part.get("text", "")).strip()
            if text:
                parts.append(text)
        elif part_type == "image":
            # OpenAI tool role content is text-only; keep signal without payload.
            parts.append("[image omitted]")
    return "\n".join(parts).strip()


def _openai_message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return str(content or "").strip()
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            text = item.strip()
            if text:
                parts.append(text)
            continue
        if not isinstance(item, dict):
            continue
        text_field = item.get("text")
        if isinstance(text_field, str):
            text = text_field.strip()
            if text:
                parts.append(text)
            continue
        if isinstance(text_field, dict):
            value = str(text_field.get("value", "")).strip()
            if value:
                parts.append(value)
            continue
        value = str(item.get("content", "")).strip()
        if value:
            parts.append(value)
    return "\n".join(parts).strip()


def _anthropic_user_blocks_to_openai_messages(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    pending_text: list[str] = []

    def _flush_pending_text() -> None:
        if not pending_text:
            return
        merged = "\n".join(part for part in pending_text if part).strip()
        pending_text.clear()
        if merged:
            messages.append({"role": "user", "content": merged})

    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type", "")).strip().lower()
        if block_type == "text":
            text = str(block.get("text", "")).strip()
            if text:
                pending_text.append(text)
            continue
        if block_type != "tool_result":
            continue
        _flush_pending_text()
        tool_call_id = str(block.get("tool_use_id", "")).strip()
        if not tool_call_id:
            continue
        tool_text = _tool_result_content_to_text(block.get("content"))
        if bool(block.get("is_error", False)):
            tool_text = f"[tool_error] {tool_text}".strip()
        if not tool_text:
            tool_text = "(empty tool result)"
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": tool_text,
            }
        )

    _flush_pending_text()
    return messages


def _anthropic_assistant_blocks_to_openai_message(blocks: list[dict[str, Any]]) -> dict[str, Any] | None:
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for idx, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type", "")).strip().lower()
        if block_type == "text":
            text = str(block.get("text", "")).strip()
            if text:
                text_parts.append(text)
            continue
        if block_type != "tool_use":
            continue
        tool_name = str(block.get("name", "")).strip()
        if not tool_name:
            continue
        tool_input = block.get("input", {})
        if not isinstance(tool_input, dict):
            tool_input = {}
        tool_call_id = str(block.get("id", "")).strip() or f"toolu_openai_{uuid.uuid4().hex[:12]}_{idx}"
        tool_calls.append(
            {
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(tool_input, ensure_ascii=True, sort_keys=True),
                },
            }
        )
    if not text_parts and not tool_calls:
        return None
    message: dict[str, Any] = {
        "role": "assistant",
        "content": "\n".join(text_parts).strip(),
    }
    if tool_calls:
        message["tool_calls"] = tool_calls
    return message


def _anthropic_messages_to_openai_messages(
    *,
    messages: list[dict[str, Any]],
    system_prompt: str,
) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    system_text = str(system_prompt or "").strip()
    if system_text:
        converted.append({"role": "system", "content": system_text})
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", "")).strip().lower()
        content = msg.get("content")
        if not isinstance(content, list):
            text = str(content or "").strip()
            if text:
                converted.append({"role": role or "user", "content": text})
            continue
        if role == "assistant":
            assistant_message = _anthropic_assistant_blocks_to_openai_message(content)
            if assistant_message is not None:
                converted.append(assistant_message)
            continue
        converted.extend(_anthropic_user_blocks_to_openai_messages(content))
    return converted


def _anthropic_tools_to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name", "")).strip()
        if not name:
            continue
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": str(tool.get("description", "")).strip(),
                    "parameters": tool.get("input_schema", {}),
                },
            }
        )
    return converted


def _openai_use_chat_completions() -> bool:
    raw = str(os.getenv("OPENAI_USE_CHAT_COMPLETIONS", "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _openai_base_url() -> str:
    base_url = str(os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).strip().rstrip("/")
    if not base_url:
        return "https://api.openai.com/v1"
    return base_url


def _anthropic_messages_to_openai_responses_input(
    *,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    converted = _anthropic_messages_to_openai_messages(messages=messages, system_prompt="")
    input_items: list[dict[str, Any]] = []
    for msg in converted:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", "")).strip().lower()
        if role in {"system", "user", "assistant"}:
            content_text = _openai_message_content_to_text(msg.get("content"))
            if role == "assistant":
                tool_calls = msg.get("tool_calls", [])
                if isinstance(tool_calls, list):
                    for call in tool_calls:
                        if not isinstance(call, dict):
                            continue
                        function = call.get("function", {})
                        if not isinstance(function, dict):
                            continue
                        tool_name = str(function.get("name", "")).strip()
                        raw_arguments = str(function.get("arguments", "")).strip()
                        call_id = str(call.get("id", "")).strip()
                        if not tool_name:
                            continue
                        # Preserve previous tool-call state in plain text so Responses
                        # input stays compatible across providers/versions.
                        call_line = f"[tool_call id={call_id or 'unknown'} name={tool_name}] {raw_arguments or '{}'}"
                        content_text = f"{content_text}\n{call_line}".strip() if content_text else call_line
            if not content_text:
                continue
            # Responses API expects role-aware content block types:
            # - user/system inputs -> input_text
            # - assistant history -> output_text
            # Sending assistant history as input_text triggers 400 invalid_value.
            content_type = "output_text" if role == "assistant" else "input_text"
            input_items.append(
                {
                    "role": role,
                    "content": [{"type": content_type, "text": content_text}],
                }
            )
            continue
        if role != "tool":
            continue
        tool_call_id = str(msg.get("tool_call_id", "")).strip() or "unknown"
        tool_content = _openai_message_content_to_text(msg.get("content"))
        if not tool_content:
            tool_content = "(empty tool result)"
        # Keep tool outputs as text items instead of function_call_output inputs.
        # This avoids schema drift between OpenAI-compatible Responses endpoints.
        input_items.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"[tool_result id={tool_call_id}]\n{tool_content}",
                    }
                ],
            }
        )
    return input_items


def _anthropic_tools_to_openai_responses_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name", "")).strip()
        if not name:
            continue
        converted.append(
            {
                "type": "function",
                "name": name,
                "description": str(tool.get("description", "")).strip(),
                "parameters": tool.get("input_schema", {}),
                "strict": True,
            }
        )
    return converted


def _openai_responses_output_to_text(payload: dict[str, Any]) -> str:
    output_text = str(payload.get("output_text", "")).strip()
    if output_text:
        return output_text
    output_items = payload.get("output", [])
    if not isinstance(output_items, list):
        return ""
    parts: list[str] = []
    for item in output_items:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type", "")).strip().lower()
        if item_type == "message":
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = str(block.get("type", "")).strip().lower()
                if block_type in {"output_text", "text"}:
                    text = str(block.get("text", "")).strip()
                    if text:
                        parts.append(text)
        elif item_type in {"output_text", "text"}:
            text = str(item.get("text", "")).strip()
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def _openai_responses_request(
    *,
    api_key: str,
    model: str,
    input_items: list[dict[str, Any]],
    instructions: str,
    tools: list[dict[str, Any]] | None,
    max_tokens: int,
    temperature: float | None,
) -> dict[str, Any]:
    url = f"{_openai_base_url()}/responses"
    base_payload: dict[str, Any] = {
        "model": model,
        "input": input_items,
    }
    instructions_text = str(instructions or "").strip()
    if instructions_text:
        base_payload["instructions"] = instructions_text
    if tools:
        base_payload["tools"] = tools
        base_payload["tool_choice"] = "auto"
    if int(max_tokens) > 0:
        base_payload["max_output_tokens"] = int(max_tokens)
    if temperature is not None:
        base_payload["temperature"] = float(temperature)

    temperature_options: list[float | None] = [None]
    if temperature is not None:
        # Keep deterministic settings when supported; fallback when rejected.
        temperature_options = [float(temperature), None]

    last_error: Exception | None = None
    for maybe_temperature in temperature_options:
        payload = dict(base_payload)
        if maybe_temperature is None:
            payload.pop("temperature", None)
        else:
            payload["temperature"] = maybe_temperature
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        request = urllib.request.Request(url=url, data=body, method="POST")
        request.add_header("Authorization", f"Bearer {api_key}")
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=max(15, int(os.getenv("OPENAI_TIMEOUT_S", "120")))) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(
                f"OpenAI responses request failed ({exc.code}): {_clip_text(error_body, max_chars=800)}"
            )
            continue
        except urllib.error.URLError as exc:
            last_error = RuntimeError(f"OpenAI responses request error: {type(exc).__name__}: {exc}")
            continue
        except Exception as exc:
            last_error = RuntimeError(f"OpenAI responses request failed: {type(exc).__name__}: {exc}")
            continue
        try:
            payload_obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"OpenAI responses returned invalid JSON: {_clip_text(raw, max_chars=800)}"
            ) from exc
        if not isinstance(payload_obj, dict):
            raise RuntimeError(
                f"OpenAI responses returned non-object payload: {_clip_text(raw, max_chars=800)}"
            )
        return payload_obj
    if last_error is not None:
        raise last_error
    raise RuntimeError("OpenAI responses request failed with unknown error.")


def _openai_chat_completions_request(
    *,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    max_tokens: int,
    temperature: float | None,
) -> dict[str, Any]:
    url = f"{_openai_base_url()}/chat/completions"

    base_payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if tools:
        base_payload["tools"] = tools
        base_payload["tool_choice"] = "auto"
    if temperature is not None:
        base_payload["temperature"] = float(temperature)

    token_fields: list[str | None] = [None]
    if int(max_tokens) > 0:
        # GPT-5 family deployments can vary by accepted cap field.
        token_fields = ["max_completion_tokens", "max_tokens"]
    temperature_options: list[float | None] = [None]
    if temperature is not None:
        # Keep deterministic settings when supported; auto-fallback if endpoint rejects it.
        temperature_options = [float(temperature), None]

    last_error: Exception | None = None
    for token_field in token_fields:
        for maybe_temperature in temperature_options:
            payload = dict(base_payload)
            if token_field is not None:
                payload[token_field] = int(max_tokens)
                other_field = "max_tokens" if token_field == "max_completion_tokens" else "max_completion_tokens"
                payload.pop(other_field, None)
            if maybe_temperature is None:
                payload.pop("temperature", None)
            else:
                payload["temperature"] = maybe_temperature
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            request = urllib.request.Request(url=url, data=body, method="POST")
            request.add_header("Authorization", f"Bearer {api_key}")
            request.add_header("Content-Type", "application/json")
            request.add_header("Accept", "application/json")
            try:
                with urllib.request.urlopen(request, timeout=max(15, int(os.getenv("OPENAI_TIMEOUT_S", "120")))) as response:
                    raw = response.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")
                last_error = RuntimeError(
                    f"OpenAI chat completion failed ({exc.code}): {_clip_text(error_body, max_chars=800)}"
                )
                continue
            except urllib.error.URLError as exc:
                last_error = RuntimeError(f"OpenAI chat completion request error: {type(exc).__name__}: {exc}")
                continue
            except Exception as exc:
                last_error = RuntimeError(f"OpenAI chat completion request failed: {type(exc).__name__}: {exc}")
                continue
            try:
                payload_obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"OpenAI chat completion returned invalid JSON: {_clip_text(raw, max_chars=800)}"
                ) from exc
            if not isinstance(payload_obj, dict):
                raise RuntimeError(
                    f"OpenAI chat completion returned non-object payload: {_clip_text(raw, max_chars=800)}"
                )
            return payload_obj
    if last_error is not None:
        raise last_error
    raise RuntimeError("OpenAI chat completion failed with unknown error.")


@dataclass(frozen=True)
class _OpenAIUsageWrapper:
    payload: dict[str, Any]

    def model_dump(self) -> dict[str, Any]:
        return dict(self.payload)


@dataclass(frozen=True)
class _OpenAITextBlock:
    text: str

    def model_dump(self) -> dict[str, Any]:
        return {"type": "text", "text": self.text}


@dataclass(frozen=True)
class _OpenAICompatResponse:
    content: list[_OpenAITextBlock]
    usage: _OpenAIUsageWrapper


class _OpenAICompatMessagesAPI:
    def __init__(self, *, api_key: str) -> None:
        self._api_key = api_key

    def create(
        self,
        *,
        model: str,
        max_tokens: int = 0,
        system: Any = "",
        messages: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        **_: Any,
    ) -> _OpenAICompatResponse:
        system_prompt = _extract_system_prompt_text(system)
        if _openai_use_chat_completions():
            payload = _openai_chat_completions_request(
                api_key=self._api_key,
                model=model,
                messages=_anthropic_messages_to_openai_messages(
                    messages=messages or [],
                    system_prompt=system_prompt,
                ),
                tools=None,
                max_tokens=max(0, int(max_tokens)),
                temperature=temperature,
            )
            choices = payload.get("choices", [])
            if not (isinstance(choices, list) and choices):
                raise RuntimeError("OpenAI chat completion returned no choices.")
            first_choice = choices[0] if isinstance(choices[0], dict) else {}
            message = first_choice.get("message", {})
            if not isinstance(message, dict):
                raise RuntimeError("OpenAI chat completion choice missing message object.")
            raw_text = _openai_message_content_to_text(message.get("content"))
            if not raw_text:
                refusal = str(message.get("refusal", "")).strip()
                raw_text = refusal or ""
            api_variant = "chat_completions"
        else:
            payload = _openai_responses_request(
                api_key=self._api_key,
                model=model,
                input_items=_anthropic_messages_to_openai_responses_input(messages=messages or []),
                instructions=system_prompt,
                tools=None,
                max_tokens=max(0, int(max_tokens)),
                temperature=temperature,
            )
            raw_text = _openai_responses_output_to_text(payload)
            api_variant = "responses"
        usage_raw = payload.get("usage", {})
        usage = usage_raw if isinstance(usage_raw, dict) else {}
        response_id = str(payload.get("id", "")).strip()
        usage_payload = {
            "backend": "openai",
            "model": model,
            "response_id": response_id,
            "api": api_variant,
            **usage,
        }
        return _OpenAICompatResponse(
            content=[_OpenAITextBlock(text=raw_text)],
            usage=_OpenAIUsageWrapper(payload=usage_payload),
        )


class _OpenAICompatClient:
    def __init__(self, *, api_key: str) -> None:
        self.messages = _OpenAICompatMessagesAPI(api_key=api_key)


def _render_message_history_for_claude_print(messages: list[dict[str, Any]]) -> str:
    return render_message_history_for_claude_print(messages, max_messages=20)


def _extract_first_json_object(raw: str) -> dict[str, Any]:
    return extract_first_json_object(raw, max_error_chars=500)


def _assistant_blocks_from_claude_print_payload(
    *,
    payload: dict[str, Any],
    allowed_tool_names: set[str],
) -> list[dict[str, Any]]:
    return assistant_blocks_from_claude_print_payload(
        payload=payload,
        allowed_tool_names=allowed_tool_names,
    )


def _create_executor_response_via_claude_print(
    *,
    model: str,
    system_prompt: str,
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    prompt_logger: Callable[[str], None] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run one executor turn via `claude -p` and return synthetic assistant blocks."""
    tool_names = [str(tool.get("name", "")).strip() for tool in tools if isinstance(tool, dict)]
    allowed_tool_names = {name for name in tool_names if name}
    tools_for_prompt = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name", "")).strip()
        if not name:
            continue
        tools_for_prompt.append(
            {
                "name": name,
                "description": str(tool.get("description", "")).strip(),
                "input_schema": tool.get("input_schema", {}),
            }
        )
    history_text = _render_message_history_for_claude_print(messages)
    prompt = (
        "You are the planner for a tool-using loop.\n"
        "Return exactly one JSON object with this shape:\n"
        "{\n"
        '  "assistant_text": "short reasoning",\n'
        '  "tool_calls": [{"name":"tool_name","input":{...}}]\n'
        "}\n"
        "Rules:\n"
        "- Use ONLY tools listed below.\n"
        "- tool_calls may contain multiple calls, or be empty if task is done.\n"
        "- input must match each tool input_schema.\n"
        "- Do not wrap JSON in markdown.\n\n"
        f"SYSTEM_PROMPT:\n{system_prompt}\n\n"
        f"TOOLS:\n{json.dumps(tools_for_prompt, ensure_ascii=True, indent=2, sort_keys=True)}\n\n"
        f"MESSAGE_HISTORY:\n{history_text}\n"
    )
    if prompt_logger is not None:
        prompt_logger(prompt)
    timeout_s = max(10, int(os.getenv("CORTEX_CLAUDE_PRINT_TIMEOUT_S", "90")))
    requested_model, effective_model = resolve_claude_print_model(
        model,
        fallback_model=DEFAULT_EXECUTOR_MODEL,
    )
    effort = normalize_claude_print_effort(None, default="high")
    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "text",
        "--tools",
        "",
        "--effort",
        effort,
    ]
    cmd.extend(["--model", effective_model])
    cmd_env = build_claude_print_env()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            env=cmd_env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"claude -p executor turn timed out after {timeout_s}s. "
            "Try lowering prompt size, using a faster model, or increasing CORTEX_CLAUDE_PRINT_TIMEOUT_S."
        ) from exc
    stdout = str(proc.stdout or "")
    stderr = str(proc.stderr or "")
    if proc.returncode != 0:
        raise RuntimeError(
            "claude -p executor turn failed "
            f"(code={proc.returncode}): {_clip_text(stderr or stdout, max_chars=800)}"
        )
    payload = _extract_first_json_object(stdout)
    blocks = _assistant_blocks_from_claude_print_payload(
        payload=payload,
        allowed_tool_names=allowed_tool_names,
    )
    usage = {
        "backend": "claude_print",
        "model": effective_model,
        "requested_model": requested_model,
        "effort": effort,
        "stdout_chars": len(stdout),
        "stderr_chars": len(stderr),
    }
    return blocks, usage


def _create_executor_response_via_openai(
    *,
    api_key: str,
    model: str,
    system_prompt: str,
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    temperature: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tool_names = [str(tool.get("name", "")).strip() for tool in tools if isinstance(tool, dict)]
    allowed_tool_names = {name for name in tool_names if name}
    assistant_blocks: list[dict[str, Any]] = []
    if _openai_use_chat_completions():
        payload = _openai_chat_completions_request(
            api_key=api_key,
            model=model,
            messages=_anthropic_messages_to_openai_messages(
                messages=messages,
                system_prompt=system_prompt,
            ),
            tools=_anthropic_tools_to_openai_tools(tools),
            max_tokens=1800,
            temperature=temperature,
        )
        choices = payload.get("choices", [])
        if not (isinstance(choices, list) and choices):
            raise RuntimeError("OpenAI executor response did not contain choices.")
        first_choice = choices[0] if isinstance(choices[0], dict) else {}
        message = first_choice.get("message", {})
        if not isinstance(message, dict):
            raise RuntimeError("OpenAI executor response missing message object.")
        assistant_text = _openai_message_content_to_text(message.get("content"))
        if assistant_text:
            assistant_blocks.append({"type": "text", "text": assistant_text})

        tool_calls = message.get("tool_calls", [])
        if tool_calls is None:
            tool_calls = []
        if not isinstance(tool_calls, list):
            raise RuntimeError(f"OpenAI executor tool_calls must be list, got {type(tool_calls).__name__}")
        for idx, call in enumerate(tool_calls):
            if not isinstance(call, dict):
                raise RuntimeError(f"OpenAI executor tool call at index {idx} must be object.")
            function = call.get("function", {})
            if not isinstance(function, dict):
                raise RuntimeError(f"OpenAI executor tool call at index {idx} missing function object.")
            name = str(function.get("name", "")).strip()
            if not name:
                raise RuntimeError(f"OpenAI executor tool call at index {idx} missing function name.")
            if name not in allowed_tool_names:
                raise RuntimeError(f"OpenAI requested unknown tool '{name}'. Allowed: {sorted(allowed_tool_names)}")
            raw_arguments = function.get("arguments", "{}")
            if isinstance(raw_arguments, dict):
                tool_input = raw_arguments
            else:
                raw_arguments_text = str(raw_arguments or "").strip() or "{}"
                try:
                    parsed = json.loads(raw_arguments_text)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"OpenAI tool call '{name}' arguments were not valid JSON: "
                        f"{_clip_text(raw_arguments_text, max_chars=500)}"
                    ) from exc
                if not isinstance(parsed, dict):
                    raise RuntimeError(f"OpenAI tool call '{name}' arguments must decode to an object.")
                tool_input = parsed
            tool_call_id = str(call.get("id", "")).strip() or f"toolu_openai_{uuid.uuid4().hex[:12]}_{idx}"
            assistant_blocks.append(
                {
                    "type": "tool_use",
                    "id": tool_call_id,
                    "name": name,
                    "input": tool_input,
                }
            )
        api_variant = "chat_completions"
    else:
        payload = _openai_responses_request(
            api_key=api_key,
            model=model,
            input_items=_anthropic_messages_to_openai_responses_input(messages=messages),
            instructions=system_prompt,
            tools=_anthropic_tools_to_openai_responses_tools(tools),
            max_tokens=1800,
            temperature=temperature,
        )
        assistant_text = _openai_responses_output_to_text(payload)
        if assistant_text:
            assistant_blocks.append({"type": "text", "text": assistant_text})
        output_items = payload.get("output", [])
        if output_items is None:
            output_items = []
        if not isinstance(output_items, list):
            raise RuntimeError(f"OpenAI executor output must be list, got {type(output_items).__name__}")
        call_index = 0
        for idx, item in enumerate(output_items):
            if not isinstance(item, dict):
                continue
            if str(item.get("type", "")).strip().lower() != "function_call":
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                raise RuntimeError(f"OpenAI function_call at output index {idx} missing name.")
            if name not in allowed_tool_names:
                raise RuntimeError(f"OpenAI requested unknown tool '{name}'. Allowed: {sorted(allowed_tool_names)}")
            raw_arguments = item.get("arguments", "{}")
            if isinstance(raw_arguments, dict):
                tool_input = raw_arguments
            else:
                raw_arguments_text = str(raw_arguments or "").strip() or "{}"
                try:
                    parsed = json.loads(raw_arguments_text)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"OpenAI function_call '{name}' arguments were not valid JSON: "
                        f"{_clip_text(raw_arguments_text, max_chars=500)}"
                    ) from exc
                if not isinstance(parsed, dict):
                    raise RuntimeError(f"OpenAI function_call '{name}' arguments must decode to an object.")
                tool_input = parsed
            # Responses API uses call_id for tool correlation; normalize it to
            # existing tool_use.id expected by the rest of the runtime.
            tool_call_id = str(item.get("call_id", "")).strip() or f"toolu_openai_{uuid.uuid4().hex[:12]}_{call_index}"
            call_index += 1
            assistant_blocks.append(
                {
                    "type": "tool_use",
                    "id": tool_call_id,
                    "name": name,
                    "input": tool_input,
                }
            )
        api_variant = "responses"

    usage_raw = payload.get("usage", {})
    usage = usage_raw if isinstance(usage_raw, dict) else {}
    usage_payload = {
        "backend": "openai",
        "model": model,
        "response_id": str(payload.get("id", "")).strip(),
        "api": api_variant,
        **usage,
    }
    return assistant_blocks, usage_payload


def _hash_base64_png(image_b64: str | None) -> str | None:
    if not isinstance(image_b64, str):
        return None
    try:
        data = base64.b64decode(image_b64.encode("ascii"), validate=True)
    except Exception:
        return None
    digest = hashlib.sha256(data).hexdigest()
    return f"sha256:{digest}"


def _normalize_coordinate(coord: Any) -> tuple[int, int] | None:
    if not (isinstance(coord, (list, tuple)) and len(coord) == 2):
        return None
    try:
        x = int(coord[0])
        y = int(coord[1])
    except (TypeError, ValueError):
        return None
    return x, y


def _normalize_region(region: Any) -> tuple[int, int, int, int] | None:
    if not (isinstance(region, (list, tuple)) and len(region) == 4):
        return None
    try:
        coords = tuple(int(value) for value in region)
    except (TypeError, ValueError):
        return None
    return coords


def _extract_computer_use_metadata(tool_input: Any, result: Any) -> dict[str, Any]:
    if not isinstance(tool_input, dict):
        return {}
    metadata: dict[str, Any] = {}

    action = tool_input.get("action")
    if isinstance(action, str) and action.strip():
        metadata["action"] = action.strip()

    coordinate = _normalize_coordinate(tool_input.get("coordinate"))
    if coordinate:
        metadata["coordinate"] = [coordinate[0], coordinate[1]]

    start = _normalize_coordinate(tool_input.get("start_coordinate"))
    if start:
        metadata["start_coordinate"] = [start[0], start[1]]
    end = _normalize_coordinate(tool_input.get("coordinate"))
    if end and start:
        metadata["end_coordinate"] = [end[0], end[1]]

    region = _normalize_region(tool_input.get("region"))
    if region:
        metadata["region"] = [region[0], region[1], region[2], region[3]]
        if metadata.get("action") == "zoom":
            metadata["zoom_region"] = metadata["region"]

    screenshot_hash = _hash_base64_png(getattr(result, "base64_image_png", None))
    if screenshot_hash:
        metadata["screenshot_hash"] = screenshot_hash

    modifiers = tool_input.get("modifiers")
    if isinstance(modifiers, (list, tuple)) and modifiers:
        metadata["modifiers"] = [str(mod).strip() for mod in modifiers if str(mod).strip()]

    return metadata


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
) -> str:
    return (
        f"{domain_fragment}"
        f"- Active task_id: {task_id}\n\n"
        "Skills metadata:\n"
        f"{skills_text}\n\n"
        "Prior lessons:\n"
        f"{lessons_text}\n"
    )


_PLACEBO_HINT_BANK: tuple[str, ...] = (
    "Re-read the task goal and verify all required outputs before stopping.",
    "Use deterministic checks and avoid guessing when a requirement is unclear.",
    "Confirm filenames, query outputs, and exact required patterns before finalizing.",
    "Prioritize contract closure over stylistic or optional cleanup steps.",
    "When errors recur, simplify the plan and verify intermediate outputs explicitly.",
)


def _placebo_hint_for_lesson(*, lesson_id: str, task_id: str, domain: str) -> str:
    token = f"{domain}|{task_id}|{lesson_id}".encode("utf-8", "ignore")
    digest = hashlib.sha256(token).hexdigest()
    idx = int(digest[:8], 16) % len(_PLACEBO_HINT_BANK)
    return f"PLACEBO_CONTROL[{digest[:6]}]: {_PLACEBO_HINT_BANK[idx]}"


def _format_v2_lesson_block(
    matches: list[Any],
    *,
    use_placebo: bool = False,
    task_id: str = "",
    domain: str = "",
) -> tuple[str, list[str]]:
    if not matches:
        return "", []
    lines = ["Memory V2 lessons (high-signal):"]
    lesson_ids: list[str] = []
    for match in matches:
        lesson = getattr(match, "lesson", None)
        score = getattr(match, "score", None)
        if lesson is None:
            continue
        lesson_id = str(getattr(lesson, "lesson_id", ""))
        lesson_ids.append(lesson_id)
        score_value = float(getattr(score, "score", 0.0) or 0.0) if score is not None else 0.0
        rule_text = (
            _placebo_hint_for_lesson(lesson_id=lesson_id, task_id=task_id, domain=domain)
            if use_placebo
            else str(getattr(lesson, "rule_text", ""))
        )
        lines.append(f"- ({score_value:.2f}) {rule_text}")
    return "\n".join(lines), [value for value in lesson_ids if value]


def _format_legacy_placebo_lesson_block(
    *,
    lessons: list[Any],
    lessons_loaded: int,
    task_id: str,
    domain: str,
) -> str:
    if lessons_loaded <= 0:
        return "No prior lessons loaded."
    lines = [
        "CRITICAL lessons from previous sessions — control placeholders (content hidden):",
    ]
    emitted = 0
    for lesson in lessons:
        if emitted >= lessons_loaded:
            break
        session_id = int(getattr(lesson, "session_id", 0) or 0)
        category = str(getattr(lesson, "category", "")).strip().lower() or "insight"
        lesson_text = str(getattr(lesson, "lesson", "")).strip()
        seed = f"{session_id}:{category}:{lesson_text[:48]}"
        lines.append(
            "- [control] "
            + _placebo_hint_for_lesson(
                lesson_id=f"legacy:{seed}",
                task_id=task_id,
                domain=domain,
            )
        )
        emitted += 1
    while emitted < lessons_loaded:
        lines.append(
            "- [control] "
            + _placebo_hint_for_lesson(
                lesson_id=f"legacy:pad:{emitted}",
                task_id=task_id,
                domain=domain,
            )
        )
        emitted += 1
    return "\n".join(lines)


def _has_promoted_v2_lesson_for_task(*, path: Path, task_id: str, domain: str) -> bool:
    normalized_domain = str(domain).strip().lower()
    for record in load_lesson_records(path):
        if str(getattr(record, "status", "")).strip().lower() != "promoted":
            continue
        if str(getattr(record, "task_id", "")).strip() != task_id:
            continue
        record_domain = str(getattr(record, "domain", "")).strip().lower()
        if record_domain and record_domain != normalized_domain:
            continue
        return True
    return False


def _select_high_signal_prerun_matches(
    *,
    matches: list[Any],
    task_id: str,
    domain: str,
    max_results: int = 4,
    min_score: float = 0.55,
) -> list[Any]:
    """
    Keep pre-run memory injection small and targeted.

    Why this exists:
    - pre-run lesson blobs can become noisy and dilute tool execution quality
    - task/domain exact matches should dominate broad historical hints
    """
    if not matches:
        return []
    normalized_domain = str(domain).strip().lower()
    limit = max(0, int(max_results))
    threshold = float(min_score)
    selected: list[Any] = []
    seen_ids: set[str] = set()

    # Pass 1: exact task+domain matches with non-trivial score.
    for match in matches:
        lesson = getattr(match, "lesson", None)
        score = getattr(match, "score", None)
        if lesson is None or score is None:
            continue
        lesson_id = str(getattr(lesson, "lesson_id", "")).strip()
        if not lesson_id or lesson_id in seen_ids:
            continue
        if str(getattr(lesson, "task_id", "")).strip() != task_id:
            continue
        if str(getattr(lesson, "domain", "")).strip().lower() != normalized_domain:
            continue
        if float(getattr(score, "score", 0.0) or 0.0) < threshold:
            continue
        selected.append(match)
        seen_ids.add(lesson_id)
        if len(selected) >= limit:
            return selected

    # Pass 2: same-domain fallback for remaining slots.
    for match in matches:
        lesson = getattr(match, "lesson", None)
        score = getattr(match, "score", None)
        if lesson is None or score is None:
            continue
        lesson_id = str(getattr(lesson, "lesson_id", "")).strip()
        if not lesson_id or lesson_id in seen_ids:
            continue
        if str(getattr(lesson, "domain", "")).strip().lower() != normalized_domain:
            continue
        if float(getattr(score, "score", 0.0) or 0.0) < threshold:
            continue
        selected.append(match)
        seen_ids.add(lesson_id)
        if len(selected) >= limit:
            break

    return selected


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
) -> set[str]:
    """Gate only on active-domain skills to prevent cross-domain deadlocks."""
    if not require_skill_read:
        return set()
    domain_prefix = f"{domain}/"
    domain_refs = [ref for ref in routed_refs if ref.startswith(domain_prefix)]
    return set(domain_refs[:1])


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
) -> CliPromptPreview:
    """Build the exact prompt/tools payload without executing a session."""
    # Workstream 1 only introduces mode plumbing; strict/legacy behavior split lands
    # in later workstreams but this keeps preview and runtime signatures aligned.
    learning_mode = _normalize_learning_mode(learning_mode)
    adapter = _resolve_adapter_with_mode(
        domain,
        cryptic_errors=cryptic_errors,
        semi_helpful_errors=semi_helpful_errors,
        mixed_errors=mixed_errors,
    )
    task_text = task.strip() if isinstance(task, str) and task.strip() else _load_task_text(TASKS_ROOT, task_id)
    if bootstrap:
        task_text = re.sub(r"- Read the .*?skill document.*?\n", "", task_text)
        task_text = re.sub(r",?\s*read_skill,?", "", task_text)

    # Prompt assembly mirrors run_cli_agent to guarantee dump parity.
    skill_manifest_entries = build_skill_manifest(skills_root=SKILLS_ROOT, manifest_path=MANIFEST_PATH)
    if bootstrap:
        routed_entries: list[SkillManifestEntry] = []
        routed_refs: list[str] = []
        required_skill_refs: set[str] = set()
        skills_text = (
            "(bootstrap mode — no skill docs available, ignore any task instructions about reading skills. "
            "Learn from trial, error messages, and prior lessons below.)"
        )
    else:
        routed_entries = route_manifest_entries(task=task_text, entries=skill_manifest_entries, top_k=2)
        routed_entries = _prioritize_domain_routed_entries(entries=routed_entries, domain=domain)
        routed_refs = [entry.skill_ref for entry in routed_entries]
        required_skill_refs = _required_skill_refs_for_domain(
            routed_refs=routed_refs,
            domain=domain,
            require_skill_read=require_skill_read,
        )
        skills_text = manifest_summaries_text(routed_entries)

    domain_keywords = adapter.quality_keywords()
    lessons_text, _ = load_relevant_lessons(
        path=LESSONS_PATH,
        task_id=task_id,
        task=task_text,
        max_lessons=12,
        max_sessions=8,
        domain_keywords=domain_keywords,
    )
    migrate_legacy_lessons(legacy_path=LESSONS_PATH, v2_path=LESSONS_V2_PATH)
    v2_matches, _ = retrieve_pre_run(
        path=LESSONS_V2_PATH,
        task_id=task_id,
        domain=domain,
        task_text=task_text,
        max_results=8,
        candidate_policy=DEFAULT_RUNTIME_CANDIDATE_POLICY,
    )
    v2_matches = _select_high_signal_prerun_matches(
        matches=v2_matches,
        task_id=task_id,
        domain=domain,
        max_results=4,
        min_score=0.55,
    )
    v2_block, _ = _format_v2_lesson_block(v2_matches)
    if v2_block:
        lessons_text = f"{lessons_text}\n\n{v2_block}".strip()
    domain_fragment = adapter.system_prompt_fragment()
    runtime_contract: dict[str, Any] | None = None
    if domain == "sqlite":
        try:
            runtime_contract, _ = load_contract(TASKS_ROOT, task_id)
        except Exception:
            runtime_contract = None
    validator_guidance = _build_sqlite_validator_guidance_from_contract(
        contract=runtime_contract or {},
        max_queries=4,
    ) if domain == "sqlite" else ""
    if validator_guidance:
        domain_fragment = f"{domain_fragment}\n{validator_guidance}\n"
    if bootstrap:
        domain_fragment = re.sub(
            r"- Before starting.*?do not guess or invent skill_ref names\.\n",
            "",
            domain_fragment,
            flags=re.DOTALL,
        )
    system_prompt = _build_system_prompt(
        task_id=task_id,
        skills_text=skills_text,
        lessons_text=lessons_text,
        domain_fragment=domain_fragment,
    )
    normalized_doc_mode = normalize_doc_mode(doc_mode)
    normalized_doc_retrieval = normalize_doc_retrieval_mode(doc_retrieval)
    if executor_docs and normalized_doc_mode != "none":
        docs_bundle = build_documentation_bundle(
            task_text=task_text,
            track_root=TRACK_ROOT,
            docs_manifest=adapter.docs_manifest(),
            documentation=documentation,
            mode=normalized_doc_mode,
            retrieval_mode=normalized_doc_retrieval,
            budget_tokens=int(doc_budget_tokens),
            retriever_model=doc_retriever_model,
            llm_client=None,
            max_chunks=10,
        )
        docs_block = docs_bundle.render_for_prompt(max_chars=8000)
        if docs_block:
            system_prompt += f"\n\n{docs_block}\n"
    if required_skill_refs:
        executor_tool = adapter.executor_tool_name
        system_prompt += (
            "\nSkill gate requirement:\n"
            f"- Before first {executor_tool} call, read at least one of: {sorted(required_skill_refs)}\n"
        )
    if opaque_tools:
        system_prompt += "\nTool names are opaque. Read your routed skills for usage semantics.\n"
    task_dir = TASKS_ROOT / task_id
    if not task_dir.exists():
        raise FileNotFoundError(f"Unknown task id: {task_id!r} (missing {task_dir})")
    fixture_refs = sorted(p.name for p in task_dir.glob("*.csv"))
    if (task_dir / "task.md").exists():
        fixture_refs.append("task.md")
    tools = adapter.tool_defs(fixture_refs, opaque=opaque_tools)
    if bootstrap:
        read_skill_api_name = "read_skill" if not opaque_tools else "probe"
        tools = [tool for tool in tools if tool.get("name") != read_skill_api_name]

    return CliPromptPreview(
        task_text=task_text,
        system_prompt=system_prompt,
        lessons_text=lessons_text,
        tools=tools,
    )


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
    judge_diagnostic: bool = False,
    contract_gap_retry: bool = DEFAULT_CONTRACT_GAP_RETRY,
    contract_gap_retry_steps: int = DEFAULT_CONTRACT_GAP_RETRY_STEPS,
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
    on_step: Callable[[int, str, bool, str | None], Any] | None = None,
) -> CliRunResult:
    normalized_learning_mode = _normalize_learning_mode(learning_mode)
    run_started_ts = time.time()
    run_started_at = format_utc_timestamp(run_started_ts)
    run_id = build_run_id(session_id=session_id, started_at_ts=run_started_ts)

    def _emit_lifecycle(event: str, *, step: int | None = None, trigger: str | None = None) -> None:
        try:
            append_lifecycle_event(
                sessions_root=SESSIONS_ROOT,
                run_id=run_id,
                session_id=session_id,
                task_id=task_id,
                domain=domain,
                learn_mode=normalized_learning_mode,
                event=event,
                step=step,
                trigger=trigger,
            )
        except Exception:
            # Telemetry must never change runtime behavior.
            return

    def _append_ledger(status: str, *, error_summary: str) -> str:
        ended_at = format_utc_timestamp(time.time())
        try:
            append_run_ledger_entry(
                sessions_root=SESSIONS_ROOT,
                run_id=run_id,
                session_id=session_id,
                task_id=task_id,
                domain=domain,
                learn_mode=normalized_learning_mode,
                started_at=run_started_at,
                ended_at=ended_at,
                status=status,
                error_summary=error_summary,
            )
        except Exception:
            return ended_at
        return ended_at

    _emit_lifecycle("queued")
    _emit_lifecycle("started")
    try:
        result = _run_cli_agent_impl(
            cfg=cfg,
            task_id=task_id,
            task=task,
            session_id=session_id,
            max_steps=max_steps,
            model_executor=model_executor,
            model_critic=model_critic,
            model_judge=model_judge,
            domain=domain,
            learning_mode=learning_mode,
            architecture_mode=architecture_mode,
            bootstrap=bootstrap,
            posttask_mode=posttask_mode,
            posttask_learn=posttask_learn,
            memory_v2_demo_mode=memory_v2_demo_mode,
            verbose=verbose,
            auto_escalate_critic=auto_escalate_critic,
            escalation_score_threshold=escalation_score_threshold,
            escalation_consecutive_runs=escalation_consecutive_runs,
            promotion_min_runs=promotion_min_runs,
            promotion_min_delta=promotion_min_delta,
            promotion_max_regressions=promotion_max_regressions,
            require_skill_read=require_skill_read,
            opaque_tools=opaque_tools,
            cryptic_errors=cryptic_errors,
            semi_helpful_errors=semi_helpful_errors,
            mixed_errors=mixed_errors,
            enable_transfer_retrieval=enable_transfer_retrieval,
            transfer_retrieval_max_results=transfer_retrieval_max_results,
            transfer_retrieval_score_weight=transfer_retrieval_score_weight,
            documentation=documentation,
            doc_mode=doc_mode,
            doc_budget_tokens=doc_budget_tokens,
            doc_retrieval=doc_retrieval,
            doc_retriever_model=doc_retriever_model,
            judge_docs=judge_docs,
            executor_docs=executor_docs,
            judge_diagnostic=judge_diagnostic,
            contract_gap_retry=contract_gap_retry,
            contract_gap_retry_steps=contract_gap_retry_steps,
            structured_lessons_required=structured_lessons_required,
            verifier_stack_enabled=verifier_stack_enabled,
            low_confidence_threshold=low_confidence_threshold,
            clarify_on_low_confidence=clarify_on_low_confidence,
            max_low_confidence_probes=max_low_confidence_probes,
            self_edit_mode=self_edit_mode,
            llm_backend=llm_backend,
            benchmark_deterministic=benchmark_deterministic,
            benchmark_promoted_only=benchmark_promoted_only,
            benchmark_placebo=benchmark_placebo,
            on_step=on_step,
            run_id=run_id,
            run_started_at=run_started_at,
            on_lifecycle_event=lambda event, payload: _emit_lifecycle(
                event,
                step=(
                    int(payload.get("step"))
                    if isinstance(payload, dict) and payload.get("step") is not None
                    else None
                ),
                trigger=(
                    str(payload.get("trigger"))
                    if isinstance(payload, dict) and payload.get("trigger")
                    else None
                ),
            ),
        )
    except KeyboardInterrupt as exc:
        summary = normalize_error_summary(str(exc) or "keyboard_interrupt")
        _emit_lifecycle("canceled")
        _append_ledger("canceled", error_summary=summary)
        raise
    except (TimeoutError, subprocess.TimeoutExpired) as exc:
        summary = normalize_error_summary(str(exc) or type(exc).__name__)
        _emit_lifecycle("timed_out")
        _append_ledger("timed_out", error_summary=summary)
        raise
    except Exception as exc:
        summary = normalize_error_summary(str(exc) or type(exc).__name__)
        _emit_lifecycle("failed")
        _append_ledger("failed", error_summary=summary)
        raise

    completion_summary = ""
    if not bool(result.metrics.get("eval_passed", False)):
        reasons = result.metrics.get("eval_reasons", [])
        if isinstance(reasons, list) and reasons:
            completion_summary = normalize_error_summary("eval_failed: " + "; ".join(str(reason) for reason in reasons[:3]))
        else:
            completion_summary = "eval_failed"
    _emit_lifecycle("completed")
    run_ended_at = _append_ledger("completed", error_summary=completion_summary)

    result.metrics["run_id"] = run_id
    result.metrics["run_started_at"] = run_started_at
    result.metrics["run_ended_at"] = run_ended_at
    result.metrics["run_status"] = "completed"
    result.metrics["run_error_summary"] = completion_summary
    write_metrics(SESSIONS_ROOT / f"session-{session_id:03d}" / "metrics.json", result.metrics)
    return result


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
    judge_diagnostic: bool = False,
    contract_gap_retry: bool = DEFAULT_CONTRACT_GAP_RETRY,
    contract_gap_retry_steps: int = DEFAULT_CONTRACT_GAP_RETRY_STEPS,
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
    on_step: Callable[[int, str, bool, str | None], Any] | None = None,
    run_id: str | None = None,
    run_started_at: str | None = None,
    on_lifecycle_event: Callable[[str, dict[str, Any]], None] | None = None,
) -> CliRunResult:
    learning_mode = _normalize_learning_mode(learning_mode)
    architecture_mode = _normalize_architecture_mode(architecture_mode)
    # Local retrieval provider is intentionally lightweight and deterministic.
    # Strict mode uses it for critic context; legacy ignores it.
    knowledge_provider = LocalDocsKnowledgeProvider()
    transfer_retrieval_max_results = max(0, int(transfer_retrieval_max_results))
    transfer_retrieval_score_weight = max(0.0, float(transfer_retrieval_score_weight))
    doc_mode = normalize_doc_mode(doc_mode)
    doc_retrieval = normalize_doc_retrieval_mode(doc_retrieval)
    doc_budget_tokens = max(128, int(doc_budget_tokens))
    contract_gap_retry_steps = max(0, min(1, int(contract_gap_retry_steps)))
    low_confidence_threshold = _clamp(float(low_confidence_threshold), 0.0, 1.0)
    max_low_confidence_probes = max(1, int(max_low_confidence_probes))
    llm_backend = _normalize_llm_backend(llm_backend)
    benchmark_deterministic = bool(benchmark_deterministic)
    benchmark_promoted_only = bool(benchmark_promoted_only)
    benchmark_placebo = bool(benchmark_placebo)
    runtime_candidate_policy = (
        CANDIDATE_POLICY_PROMOTED_ONLY
        if benchmark_promoted_only
        else DEFAULT_RUNTIME_CANDIDATE_POLICY
    )
    runtime_candidate_policy_effective = runtime_candidate_policy
    promoted_warmup_fallback = False
    if runtime_candidate_policy == CANDIDATE_POLICY_PROMOTED_ONLY and not _has_promoted_v2_lesson_for_task(
        path=LESSONS_V2_PATH,
        task_id=task_id,
        domain=domain,
    ):
        # Cold-start guard: promoted-only retrieval has no signal until at least
        # one promoted lesson exists. Fall back to anchored retrieval to bootstrap.
        runtime_candidate_policy_effective = DEFAULT_RUNTIME_CANDIDATE_POLICY
        promoted_warmup_fallback = True
    legacy_lessons_enabled = not benchmark_promoted_only
    runtime_temperature: float | None = 0.0 if benchmark_deterministic else None
    transfer_retrieval_policy = _resolve_transfer_retrieval_policy(
        enable_transfer_retrieval=enable_transfer_retrieval,
        transfer_retrieval_max_results=transfer_retrieval_max_results,
        transfer_retrieval_score_weight=transfer_retrieval_score_weight,
    )
    anthropic_api_key = str(getattr(cfg, "anthropic_api_key", "") or "").strip()
    openai_api_key = str(os.getenv("OPENAI_API_KEY", "")).strip()
    client: Any | None = None
    if llm_backend == "anthropic":
        if not anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required when llm_backend=anthropic.")
        client = anthropic.Anthropic(api_key=anthropic_api_key, max_retries=3)
    elif llm_backend == "openai":
        if not openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when llm_backend=openai.")
        client = _OpenAICompatClient(api_key=openai_api_key)
    else:
        client = ClaudePrintClient()
    adapter = _resolve_adapter_with_mode(
        domain,
        cryptic_errors=cryptic_errors,
        semi_helpful_errors=semi_helpful_errors,
        mixed_errors=mixed_errors,
    )

    # Load task text: explicit arg > task.md file > fallback
    task_text = task.strip() if isinstance(task, str) and task.strip() else _load_task_text(TASKS_ROOT, task_id)

    if bootstrap:
        # Strip read_skill references from task text to prevent wasted steps.
        # Task file unchanged on disk — only the runtime prompt is modified.
        task_text = re.sub(r"- Read the .*?skill document.*?\n", "", task_text)
        task_text = re.sub(r",?\s*read_skill,?", "", task_text)

    paths = ensure_session(session_id, sessions_root=SESSIONS_ROOT, reset_existing=True)

    # Prepare domain workspace
    task_dir = TASKS_ROOT / task_id
    if not task_dir.exists():
        raise FileNotFoundError(f"Unknown task id: {task_id!r} (missing {task_dir})")
    workspace: DomainWorkspace = adapter.prepare_workspace(task_dir, paths.session_dir)
    verification_spec = _load_verification_spec(
        tasks_root=TASKS_ROOT,
        task_id=task_id,
        task_text=task_text,
    )
    # Verification loader may provide non-fatal parse notes. Keep them in metrics
    # when available, and default to empty for backward compatibility.
    verification_spec_errors = (
        list(verification_spec.get("errors", []))
        if isinstance(verification_spec, dict)
        else []
    )

    # Build full manifest always (needed for posttask learning even in bootstrap)
    skill_manifest_entries = build_skill_manifest(skills_root=SKILLS_ROOT, manifest_path=MANIFEST_PATH)
    self_edit_manifest_entries = build_self_edit_manifest_entries(track_root=TRACK_ROOT) if bool(self_edit_mode) else []
    self_edit_mode_active = bool(self_edit_mode) and bool(self_edit_manifest_entries)
    self_edit_refs = {entry.skill_ref for entry in self_edit_manifest_entries}

    if bootstrap:
        # Bootstrap mode: no skill docs, agent must learn from scratch via lessons
        routed_entries: list[SkillManifestEntry] = []
        routed_refs: list[str] = []
        required_skill_refs: set[str] = set()
        skills_text = (
            "(bootstrap mode — no skill docs available, ignore any task instructions about reading skills. "
            "Learn from trial, error messages, and prior lessons below.)"
        )
    else:
        routed_entries = route_manifest_entries(task=task_text, entries=skill_manifest_entries, top_k=2)
        routed_entries = _prioritize_domain_routed_entries(entries=routed_entries, domain=domain)
        routed_refs = [entry.skill_ref for entry in routed_entries]
        required_skill_refs = _required_skill_refs_for_domain(
            routed_refs=routed_refs,
            domain=domain,
            require_skill_read=require_skill_read,
        )
        skills_text = manifest_summaries_text(routed_entries)
    domain_keywords = adapter.quality_keywords()
    if legacy_lessons_enabled:
        lessons_text, lessons_loaded = load_relevant_lessons(
            path=LESSONS_PATH,
            task_id=task_id,
            task=task_text,
            max_lessons=12,
            max_sessions=8,
            domain_keywords=domain_keywords,
        )
    else:
        lessons_text, lessons_loaded = "No prior lessons loaded.", 0
    # Keep V2 backward-compatible with legacy lessons by migrating legacy rows
    # into the v2 store before retrieval. The migration is idempotent.
    migrate_legacy_lessons(legacy_path=LESSONS_PATH, v2_path=LESSONS_V2_PATH)
    prerun_v2_matches, _ = retrieve_pre_run(
        path=LESSONS_V2_PATH,
        task_id=task_id,
        domain=domain,
        task_text=task_text,
        max_results=8,
        candidate_policy=runtime_candidate_policy_effective,
    )
    prerun_v2_matches = _select_high_signal_prerun_matches(
        matches=prerun_v2_matches,
        task_id=task_id,
        domain=domain,
        max_results=4,
        min_score=0.55,
    )
    prerun_v2_block, prerun_v2_ids = _format_v2_lesson_block(
        prerun_v2_matches,
        use_placebo=benchmark_placebo,
        task_id=task_id,
        domain=domain,
    )
    # Load lesson objects for error-triggered injection during the run
    loaded_lesson_objects = load_lesson_objects(
        path=LESSONS_PATH,
        task_id=task_id,
        domain_keywords=domain_keywords,
    ) if legacy_lessons_enabled else []
    if benchmark_placebo and lessons_loaded > 0:
        lessons_text = _format_legacy_placebo_lesson_block(
            lessons=loaded_lesson_objects,
            lessons_loaded=lessons_loaded,
            task_id=task_id,
            domain=domain,
        )
    if prerun_v2_block:
        lessons_text = f"{lessons_text}\n\n{prerun_v2_block}".strip()
    docs_bundle: DocumentationBundle = build_documentation_bundle(
        task_text=task_text,
        track_root=TRACK_ROOT,
        docs_manifest=adapter.docs_manifest(),
        documentation=documentation,
        mode=doc_mode,
        retrieval_mode=doc_retrieval,
        budget_tokens=doc_budget_tokens,
        retriever_model=doc_retriever_model,
        llm_client=client,
        max_chunks=10,
    )
    # Render once so metrics and runtime behavior share the exact same payload.
    docs_executor_block = docs_bundle.render_for_prompt(max_chars=9000) if executor_docs else ""
    docs_judge_block = docs_bundle.render_for_prompt(max_chars=9000) if judge_docs else ""
    docs_prompt_available = bool(docs_bundle.brief.strip())
    docs_selected_source_ids = sorted({chunk.source_id for chunk in docs_bundle.selected_chunks})
    docs_read_error_entries = [dict(row) for row in docs_bundle.load_errors]

    domain_fragment = adapter.system_prompt_fragment()
    runtime_contract: dict[str, Any] | None = None
    if domain == "sqlite":
        try:
            runtime_contract, _ = load_contract(TASKS_ROOT, task_id)
        except Exception:
            runtime_contract = None
    validator_guidance = _build_sqlite_validator_guidance_from_contract(
        contract=runtime_contract or {},
        max_queries=4,
    ) if domain == "sqlite" else ""
    if validator_guidance:
        domain_fragment = f"{domain_fragment}\n{validator_guidance}\n"
    if bootstrap:
        # Strip skill-reading instructions to avoid wasting steps on read_skill
        # with invented refs (no skill docs exist in bootstrap mode)
        domain_fragment = re.sub(
            r"- Before starting.*?do not guess or invent skill_ref names\.\n",
            "",
            domain_fragment,
            flags=re.DOTALL,
        )
    system_prompt = _build_system_prompt(
        task_id=task_id,
        skills_text=skills_text,
        lessons_text=lessons_text,
        domain_fragment=domain_fragment,
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
        system_prompt += (
            "\nTool names are opaque. Read your routed skills for usage semantics.\n"
        )

    alias_map = adapter.build_alias_map(opaque=opaque_tools)

    messages: list[dict[str, Any]] = [{"role": "user", "content": [{"type": "text", "text": task_text}]}]
    tools = adapter.tool_defs(sorted(workspace.fixture_paths.keys()), opaque=opaque_tools)
    if bootstrap:
        # Remove read_skill from tool list — no skill docs in bootstrap mode
        read_skill_api_name = "read_skill" if not opaque_tools else "probe"
        tools = [t for t in tools if t.get("name") != read_skill_api_name]
    # Build a name->schema map for tool-agnostic input validation. This keeps
    # validation structural (required keys, primitive types) instead of semantic.
    tool_schema_map = build_tool_schema_map(tools)

    escalation_state = _load_escalation_state(base_model=model_critic)
    critic_model_for_run, escalation_state = _resolve_critic_model_for_run(
        base_model=model_critic,
        auto_escalate=auto_escalate_critic,
        state=escalation_state,
    )

    contract_path = TASKS_ROOT / task_id / "CONTRACT.json"
    has_contract = contract_path.exists()

    # Simplified architecture removes the separate judge model and reuses executor.
    if architecture_mode == "simplified":
        effective_judge_model = model_executor
    elif llm_backend == "openai":
        # Keep OpenAI runs self-contained unless caller explicitly overrides judge model.
        effective_judge_model = model_judge or model_executor
    else:
        effective_judge_model = model_judge or default_judge_model(model_executor)

    loop_watchdog_state_path = state_path_for_learning_root(learning_root=LEARNING_ROOT)
    loop_watchdog_state: LoopWatchdogState = load_watchdog_state(state_path=loop_watchdog_state_path)
    loop_watchdog_decision: LoopWatchdogDecision | None = None
    loop_watchdog_failure_signals: list[str] = []
    loop_watchdog_safe_mode_active = bool(loop_watchdog_state.safe_mode_active)
    loop_watchdog_stop_flag = bool(loop_watchdog_state.last_stop_flag)

    metrics: dict[str, Any] = {
        "run_id": str(run_id or ""),
        "run_started_at": str(run_started_at or ""),
        "run_ended_at": None,
        "run_status": "started",
        "run_error_summary": "",
        "session_id": session_id,
        "task_id": task_id,
        "task": task_text,
        "domain": domain,
        "learning_mode": learning_mode,
        "architecture_mode": architecture_mode,
        "bootstrap": bootstrap,
        "mixed_errors": mixed_errors,
        "steps": 0,
        "tool_actions": 0,
        "tool_errors": 0,
        "tool_validation_errors": 0,
        "tool_validation_retry_attempts": 0,
        "tool_validation_retry_capped_events": 0,
        "skill_gate_blocks": 0,
        "skill_reads": 0,
        "required_skill_refs": sorted(required_skill_refs),
        "require_skill_read": require_skill_read,
        "lessons_loaded": lessons_loaded,
        "v2_lessons_loaded": len(prerun_v2_ids),
        "v2_prerun_lesson_ids": prerun_v2_ids,
        "v2_prerun_lesson_activations": len(prerun_v2_ids),
        "v2_prerun_placebo_applied": bool(benchmark_placebo and prerun_v2_ids),
        "lesson_activations": 0,
        "v2_lesson_activations": 0,
        "v2_lesson_activations_effective": 0 if benchmark_placebo else len(prerun_v2_ids),
        "v2_lesson_activations_placebo": len(prerun_v2_ids) if benchmark_placebo else 0,
        "v2_lesson_activations_by_step": {},
        "v2_lesson_activations_by_step_effective": {},
        "v2_lesson_activations_per_run": 0,
        "v2_lesson_activations_per_run_effective": 0,
        "v2_lesson_activation_rate": 0.0,
        "v2_lesson_activation_lane_counts": {},
        "v2_lesson_activation_lane_counts_effective": {},
        "v2_error_events": 0,
        "v2_retrieval_help_ratio": 0.0,
        "v2_retrieval_help_ratio_effective": 0.0,
        "v2_transfer_retrieval_enabled": transfer_retrieval_policy != TRANSFER_POLICY_OFF,
        "v2_transfer_retrieval_policy": transfer_retrieval_policy,
        "v2_transfer_retrieval_max_results": transfer_retrieval_max_results,
        "v2_transfer_retrieval_score_weight": transfer_retrieval_score_weight,
        "doc_mode": doc_mode,
        "doc_retrieval_mode": doc_retrieval,
        "doc_budget_tokens": doc_budget_tokens,
        "doc_retriever_model": str(doc_retriever_model or "").strip() or None,
        "executor_docs": bool(executor_docs),
        "judge_docs": bool(judge_docs),
        "judge_diagnostic": bool(judge_diagnostic),
        "contract_gap_retry_enabled": bool(contract_gap_retry),
        "contract_gap_retry_steps_budget": int(contract_gap_retry_steps),
        "verifier_stack_enabled": bool(verifier_stack_enabled),
        "verifier_low_confidence_threshold": round(float(low_confidence_threshold), 3),
        "verifier_clarify_on_low_confidence": bool(clarify_on_low_confidence),
        "verifier_max_low_confidence_probes": int(max_low_confidence_probes),
        "verifier_spec_source": str(verification_spec.get("source", "")),
        "verifier_spec_source_path": str(verification_spec.get("source_path", "")),
        "verifier_spec_exact_output_lines": int(len(verification_spec.get("exact_output_lines", []) or [])),
        "verifier_spec_required_files": int(len(verification_spec.get("required_files", []) or [])),
        "verifier_spec_required_file_patterns": int(
            sum(
                len(row.get("patterns", []))
                for row in (verification_spec.get("required_file_content_patterns", []) or [])
                if isinstance(row, dict)
            )
        ),
        "verifier_spec_required_queries": int(len(verification_spec.get("required_queries", []) or [])),
        "verifier_confidence_base": None,
        "verifier_low_confidence_triggered": False,
        "verifier_probe_status": "not_run",
        "verifier_probe_results": [],
        "verifier_probe_failures": 0,
        "verifier_override_applied": False,
        "verifier_clarifying_question": "",
        "contract_gap_retry_attempts": 0,
        "contract_gap_retry_triggered": 0,
        "contract_gap_unresolved_count_prestop": 0,
        "contract_gap_unresolved_count_final": 0,
        "contract_closure_checks": 0,
        "contract_closure_check_failures": 0,
        "contract_closure_check_last_status": "not_run",
        "contract_closure_check_last_missing": [],
        "contract_validator_runs": 0,
        "contract_validator_last_status": "none",
        "contract_validator_query_ids": [],
        "docs_raw_count": len(docs_bundle.raw_docs),
        "docs_selected_chunks_count": len(docs_bundle.selected_chunks),
        "docs_selected_source_ids": docs_selected_source_ids,
        "docs_brief_chars": len(docs_bundle.brief),
        "docs_brief_strategy": docs_bundle.brief_strategy,
        "docs_distillation_used": docs_bundle.brief_strategy == "lossy_llm",
        "docs_prompt_available": docs_prompt_available,
        "docs_executor_prompt_chars": len(docs_executor_block),
        "docs_judge_prompt_chars": len(docs_judge_block),
        "docs_executor_prompt_injected": bool(docs_executor_block),
        "docs_judge_prompt_injected": bool(docs_judge_block),
        "docs_read_error_count": len(docs_read_error_entries),
        "docs_read_errors": docs_read_error_entries,
        "llm_backend": llm_backend,
        "benchmark_deterministic": bool(benchmark_deterministic),
        "benchmark_promoted_only": bool(benchmark_promoted_only),
        "benchmark_placebo": bool(benchmark_placebo),
        "runtime_candidate_policy": runtime_candidate_policy,
        "runtime_candidate_policy_effective": runtime_candidate_policy_effective,
        "runtime_promoted_warmup_fallback": bool(promoted_warmup_fallback),
        "legacy_lessons_enabled": bool(legacy_lessons_enabled),
        "runtime_temperature": runtime_temperature,
        "v2_transfer_lane_activations": 0,
        "v2_reflection_prompts": 0,
        "v2_reflection_reasons": [],
        "v2_dependency_fallback_checks": 0,
        "v2_promoted": 0,
        "v2_suppressed": 0,
        "v2_fingerprint_recurrence_before": 0,
        "v2_fingerprint_recurrence_after": 0,
        "lessons_generated": 0,
        "v2_lessons_generated": 0,
        "posttask_patch_attempted": False,
        "self_edit_mode": bool(self_edit_mode_active),
        "self_edit_targets": sorted(self_edit_refs),
        "self_edit_forced_direct_mode": False,
        "self_edit_gate_events": 0,
        "posttask_skill_patching_skipped_by_mode": False,
        "posttask_skill_patching_skip_reason": None,
        "posttask_candidates_queued": 0,
        "posttask_patch_applied": 0,
        "posttask_rejection_counts": {
            "parse_fail": 0,
            "required_digest_mismatch": 0,
            "duplicate_jaccard": 0,
            "replace_miss": 0,
        },
        "auto_promotion_applied": 0,
        "auto_promotion_reason": None,
        "memory_v2_demo_mode": bool(memory_v2_demo_mode),
        "executor_model": model_executor,
        "critic_model": critic_model_for_run,
        "judge_model": effective_judge_model,
        "eval_score": 0.0,
        "eval_reasons": [],
        "eval_passed": False,
        "deterministic_probe_source": "none",
        "deterministic_probe_applicable": False,
        "deterministic_probe_passed": False,
        "deterministic_probe_score": 0.0,
        "deterministic_probe_reasons": [],
        "deterministic_probe_evidence": {},
        "verification_spec_source": str(verification_spec.get("source", "none")) if verification_spec is not None else "none",
        "verification_spec_errors": list(verification_spec_errors),
        "judge_score": None,
        "judge_passed": None,
        "judge_invoked": False,
        "judge_reasons": [],
        "judge_doc_grounding": [],
        "judge_critique": "",
        "judge_fail_probe_pass": False,
        "judge_pass_probe_fail": False,
        "critic_raw_lessons": [],
        "critic_filtered_lessons": [],
        "critic_rejected_lessons": [],
        "loop_watchdog_enabled": True,
        "loop_watchdog_state_path": str(loop_watchdog_state_path),
        "loop_watchdog_safe_mode_initial": bool(loop_watchdog_state.safe_mode_active),
        "loop_watchdog_safe_mode_active": bool(loop_watchdog_safe_mode_active),
        "loop_watchdog_safe_mode_triggered": False,
        "loop_watchdog_failure_signals": [],
        "loop_watchdog_disable_self_edit": False,
        "loop_watchdog_disable_posttask_patching": False,
        "loop_watchdog_stop_flag": bool(loop_watchdog_stop_flag),
        "loop_watchdog_repeated_hard_failure_signatures": 0,
        "loop_watchdog_contract_gap_unresolved_count": 0,
        "loop_watchdog_rejection_streak_initial": int(loop_watchdog_state.rejection_streak),
        "loop_watchdog_rejection_streak_final": int(loop_watchdog_state.rejection_streak),
        "loop_watchdog_safe_mode_failure_streak": int(loop_watchdog_state.safe_mode_failure_streak),
        "loop_watchdog_posttask_rejection_total": 0,
        "loop_watchdog_state_persisted": False,
        "critic_no_updates_streak": int(escalation_state.get("critic_no_updates_streak", 0)),
        "low_score_streak": int(escalation_state.get("low_score_streak", 0)),
        "escalation_state": {
            "tier": escalation_state.get("tier"),
            "override_runs_remaining": escalation_state.get("override_runs_remaining"),
            "last_trigger": escalation_state.get("last_trigger"),
            "auto_escalate_critic": auto_escalate_critic,
        },
        "usage": [],
        "time_start": time.time(),
    }

    executor_tool_name = adapter.executor_tool_name
    read_skill_refs: set[str] = set()
    run_error_events: list[ErrorEvent] = []
    seen_error_fingerprints: list[str] = []
    reflection_pending: str | None = None
    reflection_threshold_triggered = False
    reflection_fingerprints: set[str] = set()
    contract_gap_retries_used = 0
    contract_gap_prestop_artifacts: list[str] = []
    latest_unresolved_gaps: list[dict[str, Any]] = []
    dependency_setup_retries: Counter[str] = Counter()
    dependency_setup_reflections: set[str] = set()
    hard_failure_count = 0
    lesson_activation_records: list[dict[str, Any]] = []
    if prerun_v2_ids:
        lesson_activation_records.append(
            {
                "step": 0,
                "fingerprint": f"prerun:{task_id}:{domain}",
                "trigger": "pre_run_prompt",
                "lesson_ids": list(prerun_v2_ids),
                "lesson_lanes": {lesson_id: "prerun" for lesson_id in prerun_v2_ids},
                "placebo_applied": bool(benchmark_placebo),
            }
        )
    contradiction_loser_counts: dict[str, int] = defaultdict(int)
    repeated_error_signatures: list[str] = []
    promoted_lesson_ids: list[str] = []
    suppressed_lesson_ids: list[str] = []
    v2_candidate_lessons: list[dict[str, Any]] = []
    executor_input_bundles: list[dict[str, Any]] = []
    judge_input_bundle: dict[str, Any] | None = None
    judge_payload_bundle: dict[str, Any] | None = None

    def _maybe_inject_contract_gap_retry(*, current_step: int, trigger: str) -> bool:
        nonlocal contract_gap_retries_used, latest_unresolved_gaps
        if (
            not has_contract
            or not bool(contract_gap_retry)
            or contract_gap_retries_used >= int(contract_gap_retry_steps)
        ):
            return False

        # Evaluate unresolved contract gaps from actual run artifacts and use
        # the deterministic result to drive one targeted retry prompt.
        prestop_events = _canonicalize_hotfix_transfer_eval_events(
            events=read_events(paths.events_path),
            workspace=workspace,
            task_id=task_id,
        )
        prestop_eval = evaluate_cli_session(
            task=task_text,
            task_id=task_id,
            events=prestop_events,
            db_path=workspace.work_dir / "task.db",
            tasks_root=TASKS_ROOT,
        ).to_dict()
        unresolved_gaps = unresolved_contract_gaps(prestop_eval)
        validator_evidence: list[str] = []

        closure_check = _run_shell_hotfix_transfer_closure_check(
            workspace=workspace,
            task_id=task_id,
        )
        if bool(closure_check.get("applicable", False)):
            metrics["contract_closure_checks"] = int(metrics.get("contract_closure_checks", 0) or 0) + 1
            closure_missing = closure_check.get("missing_gaps", [])
            if isinstance(closure_missing, list) and closure_missing:
                metrics["contract_closure_check_failures"] = (
                    int(metrics.get("contract_closure_check_failures", 0) or 0) + 1
                )
                existing_signatures = {
                    str(row.get("gap_signature", "")).strip()
                    for row in unresolved_gaps
                    if isinstance(row, dict)
                }
                for row in closure_missing:
                    if not isinstance(row, dict):
                        continue
                    signature = str(row.get("gap_signature", "")).strip()
                    if signature and signature not in existing_signatures:
                        unresolved_gaps.append(row)
                        existing_signatures.add(signature)
            last_missing = [
                str(row.get("detail", "")).strip()
                for row in (closure_missing if isinstance(closure_missing, list) else [])
                if isinstance(row, dict) and str(row.get("detail", "")).strip()
            ]
            metrics["contract_closure_check_last_missing"] = last_missing
            metrics["contract_closure_check_last_status"] = (
                "pass" if bool(closure_check.get("passed", False)) else "fail"
            )
            evidence_rows = closure_check.get("evidence", [])
            if isinstance(evidence_rows, list):
                validator_evidence.extend(
                    [str(row).strip() for row in evidence_rows if str(row).strip()]
                )
            write_event(
                paths.events_path,
                {
                    "step": current_step,
                    "tool": "contract_closure_check",
                    "tool_input": {
                        "task_id": task_id,
                        "attempt": contract_gap_retries_used + 1,
                    },
                    "ok": bool(closure_check.get("passed", False)),
                    "error": None if bool(closure_check.get("passed", False)) else "closure_gaps_detected",
                    "output": json.dumps(closure_check, ensure_ascii=True),
                },
            )

        latest_unresolved_gaps = unresolved_gaps
        metrics["contract_gap_unresolved_count_prestop"] = int(len(unresolved_gaps))
        prestop_artifact_path = paths.session_dir / f"contract_gap_prestop_attempt_{contract_gap_retries_used + 1}.json"
        prestop_artifact_path.write_text(
            json.dumps(
                {
                    "step": current_step,
                    "attempt": contract_gap_retries_used + 1,
                    "trigger": trigger,
                    "eval_result": prestop_eval,
                    "closure_check": closure_check,
                    "unresolved_gaps": unresolved_gaps,
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        contract_gap_prestop_artifacts.append(str(prestop_artifact_path))
        if not unresolved_gaps:
            return False

        metrics["contract_gap_retry_attempts"] = int(metrics.get("contract_gap_retry_attempts", 0) or 0) + 1
        metrics["contract_gap_retry_triggered"] = int(metrics.get("contract_gap_retry_triggered", 0) or 0) + 1
        contract_gap_retries_used += 1
        gap_query = " | ".join(
            f"{row.get('reason_code', '')}:{row.get('gap_type', '')}:{row.get('detail', '')}"
            for row in unresolved_gaps[:4]
        )
        gap_tags = [
            str(row.get("reason_code", "")).strip()
            for row in unresolved_gaps
            if str(row.get("reason_code", "")).strip()
        ] + [
            str(row.get("gap_type", "")).strip()
            for row in unresolved_gaps
            if str(row.get("gap_type", "")).strip()
        ]
        # Deterministic sqlite validator run (machine-executed) before retry.
        # This provides concrete state evidence to the agent, not just prose.
        if domain == "sqlite":
            required_queries = prestop_eval.get("evidence", {}).get("required_queries", [])
            if isinstance(required_queries, list):
                mismatched_queries = [
                    row for row in required_queries
                    if isinstance(row, dict) and not bool(row.get("matched", False))
                ]
                query_sqls = [
                    str(row.get("sql", "")).strip()
                    for row in mismatched_queries
                    if str(row.get("sql", "")).strip()
                ]
                query_ids = [
                    str(row.get("id", "")).strip()
                    for row in mismatched_queries
                    if str(row.get("id", "")).strip()
                ]
                if query_sqls:
                    validator_sql = ";\n".join(query_sqls)
                    if not validator_sql.endswith(";"):
                        validator_sql += ";"
                    validator_result = adapter.execute(
                        adapter.executor_tool_name,
                        {"sql": validator_sql},
                        workspace,
                    )
                    metrics["contract_validator_runs"] = int(metrics.get("contract_validator_runs", 0) or 0) + 1
                    metrics["contract_validator_query_ids"] = query_ids
                    metrics["contract_validator_last_status"] = "ok" if not validator_result.is_error() else "error"
                    write_event(
                        paths.events_path,
                        {
                            "step": current_step,
                            "tool": "contract_validator",
                            "tool_input": {"query_ids": query_ids, "sql": validator_sql},
                            "ok": not validator_result.is_error(),
                            "error": validator_result.error,
                            "output": validator_result.output,
                        },
                    )
                    if validator_result.output:
                        validator_evidence.append(_clip_text(str(validator_result.output), max_chars=900))
                    if validator_result.error:
                        validator_evidence.append(f"validator_error={_clip_text(str(validator_result.error), max_chars=400)}")

        gap_matches, _ = retrieve_on_error(
            path=LESSONS_V2_PATH,
            error_text=gap_query,
            fingerprint="",
            domain=domain,
            task_id=task_id,
            query_tags=gap_tags,
            max_results=2,
            include_domainless=False,
            enable_transfer=enable_transfer_retrieval,
            transfer_policy=transfer_retrieval_policy,
            transfer_max_results=transfer_retrieval_max_results,
            transfer_score_weight=transfer_retrieval_score_weight,
            unresolved_gaps=unresolved_gaps,
            candidate_policy=runtime_candidate_policy_effective,
        )
        gap_hints: list[str] = []
        for match in gap_matches:
            lesson = getattr(match, "lesson", None)
            if lesson is None:
                continue
            lesson_id = str(getattr(lesson, "lesson_id", "")).strip()
            hint_text = (
                _placebo_hint_for_lesson(lesson_id=lesson_id, task_id=task_id, domain=domain)
                if benchmark_placebo
                else str(getattr(lesson, "rule_text", "")).strip()
            )
            if hint_text:
                gap_hints.append(hint_text)
        if gap_matches:
            gap_lanes: dict[str, str] = {}
            for match in gap_matches:
                lesson_id = str(getattr(match.lesson, "lesson_id", "")).strip()
                if not lesson_id:
                    continue
                lane = str(getattr(match, "lane", "strict")).strip().lower() or "strict"
                gap_lanes[lesson_id] = lane
                if lane == "transfer":
                    metrics["v2_transfer_lane_activations"] += 1
            # Record contract-gap retrieval activations so mechanism metrics
            # reflect both on-error injection and deterministic retry guidance.
            gap_fingerprint = "contract_gap:" + "|".join(
                str(row.get("gap_signature", "")).strip()
                for row in unresolved_gaps[:3]
                if str(row.get("gap_signature", "")).strip()
            )
            lesson_activation_records.append(
                {
                    "step": current_step,
                    "fingerprint": gap_fingerprint,
                    "trigger": "contract_gap_retry",
                    "lesson_ids": list(gap_lanes.keys()),
                    "lesson_lanes": gap_lanes,
                    "placebo_applied": bool(benchmark_placebo),
                }
            )
            metrics["lesson_activations"] += len(gap_lanes)
            metrics["v2_lesson_activations"] += len(gap_lanes)
            if benchmark_placebo:
                metrics["v2_lesson_activations_placebo"] += len(gap_lanes)
            else:
                metrics["v2_lesson_activations_effective"] += len(gap_lanes)
        retry_prompt = _format_contract_gap_retry_prompt(
            unresolved_gaps=unresolved_gaps,
            injected_hints=gap_hints,
            validator_evidence=validator_evidence,
        )
        messages.append({"role": "user", "content": [{"type": "text", "text": retry_prompt}]})
        write_event(
            paths.events_path,
            {
                "step": current_step,
                "tool": "contract_gap_retry",
                "tool_input": {
                    "attempt": contract_gap_retries_used,
                    "trigger": trigger,
                    "unresolved_gaps": unresolved_gaps,
                },
                "ok": True,
                "error": None,
                "output": "retry_prompt_injected",
            },
        )
        if on_lifecycle_event is not None:
            try:
                on_lifecycle_event(
                    "contract_gap_retry",
                    {
                        "step": current_step,
                        "trigger": trigger,
                    },
                )
            except Exception:
                pass
        if verbose:
            print(
                (
                    f"[step {current_step:03d}] contract gaps detected ({len(unresolved_gaps)}), "
                    f"trigger={trigger}; injecting one retry."
                ),
                flush=True,
            )
        return True

    step = 1
    validation_retries_this_step = 0
    validation_retry_capped_this_step = False
    while step <= max_steps:
        metrics["steps"] = step
        if on_lifecycle_event is not None:
            try:
                on_lifecycle_event("step", {"step": step})
            except Exception:
                pass
        if reflection_pending:
            # Force a brief self-diagnosis before the next tool call. This is
            # domain-agnostic and helps break repeated failure loops.
            messages.append({"role": "user", "content": [{"type": "text", "text": reflection_pending}]})
            reflection_pending = None
        # Persist exact executor inputs for this turn before any model call.
        executor_input_bundle: dict[str, Any] = {
            "step": step,
            "backend": llm_backend,
            "model": model_executor,
            "system_prompt": system_prompt,
            "messages": _clone_json(messages),
            "tools": _clone_json(tools),
        }
        executor_input_bundles.append(executor_input_bundle)
        if llm_backend == "anthropic":
            if client is None:
                raise RuntimeError("Anthropic client unavailable while llm_backend=anthropic.")
            request: dict[str, Any] = {
                "model": model_executor,
                "max_tokens": 1800,
                "system": system_prompt,
                "tools": tools,
                "messages": messages,
            }
            if runtime_temperature is not None:
                request["temperature"] = float(runtime_temperature)
            response = client.messages.create(**request)
            try:
                usage = response.usage.model_dump()  # type: ignore[attr-defined]
            except Exception:
                usage_obj = getattr(response, "usage", None)
                usage = usage_obj.model_dump() if usage_obj is not None and hasattr(usage_obj, "model_dump") else {}
            assistant_blocks = [block.model_dump() for block in response.content]  # type: ignore[attr-defined]
        elif llm_backend == "openai":
            assistant_blocks, usage = _create_executor_response_via_openai(
                api_key=openai_api_key,
                model=model_executor,
                system_prompt=system_prompt,
                tools=tools,
                messages=messages,
                temperature=runtime_temperature,
            )
        else:
            assistant_blocks, usage = _create_executor_response_via_claude_print(
                model=model_executor,
                system_prompt=system_prompt,
                tools=tools,
                messages=messages,
                prompt_logger=lambda prompt_text: executor_input_bundle.__setitem__("claude_print_prompt", prompt_text),
            )
        metrics["usage"].append(usage)
        messages.append({"role": "assistant", "content": assistant_blocks})
        tool_results: list[dict[str, Any]] = []
        retry_same_step = False
        saw_non_validation_tool_call = False

        for block in assistant_blocks:
            if not (isinstance(block, dict) and block.get("type") == "tool_use"):
                continue
            tool_name_raw = str(block.get("name", ""))
            canonical_name = alias_map.get(tool_name_raw, tool_name_raw)
            tool_use_id = str(block.get("id", ""))
            tool_input_raw = block.get("input", {})
            tool_input = tool_input_raw if isinstance(tool_input_raw, dict) else {}
            metrics["tool_actions"] += 1
            memory_v2_payload: dict[str, Any] = {}

            # Tool-agnostic structural validation happens before execution. This
            # prevents obviously malformed calls from wasting a tool step.
            schema = tool_schema_map.get(canonical_name) or tool_schema_map.get(tool_name_raw)
            validation_error = validate_tool_input(
                tool_name=canonical_name,
                tool_input=tool_input_raw,
                schema=schema,
            )
            is_validation_failure = bool(validation_error)
            if validation_error:
                metrics["tool_validation_errors"] += 1
                result = ToolResult(error=validation_error)
                if validation_retries_this_step < MAX_VALIDATION_RETRIES_PER_STEP:
                    # Retry malformed tool calls on the same step so schema
                    # misses do not consume the run's execution budget.
                    validation_retries_this_step += 1
                    metrics["tool_validation_retry_attempts"] += 1
                    retry_same_step = True
                else:
                    retry_same_step = False
                    if not validation_retry_capped_this_step:
                        metrics["tool_validation_retry_capped_events"] += 1
                        validation_retry_capped_this_step = True
                    if not reflection_pending:
                        validation_fingerprint = f"validation:{canonical_name}:{validation_retries_this_step}"
                        reflection_pending = _build_reflection_prompt(
                            error_text=validation_error,
                            fingerprint=validation_fingerprint,
                            reason="validation_retry_cap",
                        )
                        metrics["v2_reflection_prompts"] += 1
                        metrics["v2_reflection_reasons"].append(
                            {
                                "step": step,
                                "fingerprint": validation_fingerprint,
                                "reason": "validation_retry_cap",
                            }
                        )
            elif canonical_name == READ_SKILL_TOOL_NAME:
                metrics["skill_reads"] += 1
                skill_ref = tool_input.get("skill_ref")
                if not isinstance(skill_ref, str):
                    result = ToolResult(error=f"read_skill requires string skill_ref, got {skill_ref!r}")
                else:
                    content, err = resolve_skill_content(skill_manifest_entries, skill_ref)
                    if err:
                        result = ToolResult(error=err)
                    else:
                        read_skill_refs.add(skill_ref)
                        result = ToolResult(output=_clip_text(f"skill_ref: {skill_ref}\n\n{content}", max_chars=6000))
            elif canonical_name == SHOW_FIXTURE_TOOL_NAME:
                path_ref = tool_input.get("path_ref")
                if not isinstance(path_ref, str):
                    result = ToolResult(error=f"show_fixture requires string path_ref, got {path_ref!r}")
                else:
                    # Read fixture from workspace
                    key = path_ref.strip()
                    target = workspace.fixture_paths.get(key)
                    if target is None:
                        result = ToolResult(error=f"Unknown path_ref: {path_ref!r}. Allowed: {sorted(workspace.fixture_paths.keys())}")
                    elif not target.exists():
                        result = ToolResult(error=f"Missing fixture file: {target}")
                    else:
                        try:
                            text = target.read_text(encoding="utf-8")
                            result = ToolResult(output=_clip_text(f"path_ref: {path_ref}\n\n{text}", max_chars=6000))
                        except Exception as exc:
                            result = ToolResult(error=f"Failed reading fixture: {type(exc).__name__}: {exc}")
            elif canonical_name == executor_tool_name:
                # Skill gate check before executor
                if require_skill_read and not _is_skill_gate_satisfied(
                    read_skill_refs=read_skill_refs,
                    required_skill_refs=required_skill_refs,
                ):
                    metrics["skill_gate_blocks"] += 1
                    result = ToolResult(
                        error=(
                            f"Skill gate: call read_skill for at least one routed skill before {executor_tool_name}. "
                            f"Required refs: {sorted(required_skill_refs)}"
                        )
                    )
                else:
                    # Delegate to domain adapter
                    result = adapter.execute(canonical_name, tool_input, workspace)
                    if not result.is_error():
                        result = ToolResult(output=_clip_text(result.output or "(ok)"))
            else:
                result = ToolResult(error=f"Unknown tool requested: {tool_name_raw!r}")
            if not is_validation_failure:
                saw_non_validation_tool_call = True

            computer_metadata: dict[str, Any] = {}
            if canonical_name == COMPUTER_TOOL_NAME:
                computer_metadata = _extract_computer_use_metadata(tool_input, result)

            # Memory V2 capture + retrieval path:
            # - capture failure events via universal channels
            # - fetch fingerprint-aligned hints in the same run
            # - fallback to legacy lesson matcher if V2 has no signal yet
            capture_tool = canonical_name == executor_tool_name or canonical_name == COMPUTER_TOOL_NAME
            if result.is_error() and capture_tool and not is_validation_failure:
                error_text = result.error or ""
                action_state = {
                    "tool": canonical_name,
                    "tool_input": tool_input,
                    "step": step,
                    "task_id": task_id,
                    "domain": domain,
                }
                if computer_metadata:
                    action_state.setdefault("tool_input", {})
                    action_state["tool_input"]["computer_metadata"] = computer_metadata
                error_fingerprint = build_error_fingerprint(error=error_text, state=action_state, action=tool_input)
                error_tags = extract_tags(error=error_text, state=action_state, action=tool_input)

                failure_events = [
                    ErrorEvent(
                        channel="hard_failure",
                        error=error_text,
                        state=action_state,
                        action=tool_input,
                        tags=tuple(error_tags),
                        fingerprint=error_fingerprint,
                        metadata={"session_id": session_id, "step": step},
                    )
                ]
                # Track hard failures separately from channel fan-out so we can
                # gate reflection on true error count, not per-channel events.
                hard_failure_count += 1
                if any(tag in {"constraint", "constraint_failed"} for tag in error_tags):
                    failure_events.append(
                        ErrorEvent(
                            channel="constraint_failure",
                            error=error_text,
                            state=action_state,
                            action=tool_input,
                            tags=tuple(error_tags),
                            fingerprint=error_fingerprint,
                            metadata={"session_id": session_id, "step": step},
                        )
                    )
                if seen_error_fingerprints.count(error_fingerprint) >= 1:
                    # Repeated fingerprint in one run is a generic "no progress"
                    # signal and should be tracked independent of domain semantics.
                    failure_events.append(
                        ErrorEvent(
                            channel="progress_signal",
                            error="no_progress",
                            state=action_state,
                            action=tool_input,
                            tags=tuple(sorted(set(error_tags) | {"no_progress", "state_stall"})),
                            fingerprint=error_fingerprint,
                            metadata={"session_id": session_id, "step": step, "progress_signal": -1.0},
                        )
                    )
                if step >= max(3, int(max_steps * 0.5)):
                    failure_events.append(
                        ErrorEvent(
                            channel="efficiency_signal",
                            error="efficiency_regression",
                            state=action_state,
                            action=tool_input,
                            tags=tuple(sorted(set(error_tags) | {"efficiency_signal"})),
                            fingerprint=error_fingerprint,
                            metadata={"session_id": session_id, "step": step, "efficiency_signal": -1.0},
                        )
                    )

                memory_events_path = paths.session_dir / "memory_events.jsonl"
                for event in failure_events:
                    event_row = event.to_dict()
                    if computer_metadata:
                        event_row.setdefault("metadata", {})["computer_metadata"] = computer_metadata
                    write_event(memory_events_path, event_row)
                    write_event(MEMORY_EVENTS_PATH, event_row)
                    run_error_events.append(event)
                    metrics["v2_error_events"] += 1
                seen_error_fingerprints.append(error_fingerprint)

                reflection_reason = ""
                dependency_reflection = False
                if _is_dependency_or_setup_failure(error_text=error_text, error_tags=error_tags):
                    dependency_setup_retries[error_fingerprint] += 1

                if (
                    error_fingerprint not in dependency_setup_reflections
                    and dependency_setup_retries.get(error_fingerprint, 0) >= DEPENDENCY_SETUP_REPEAT_THRESHOLD
                ):
                    # Deterministic fallback check for repeated setup/dependency
                    # failures. This is fingerprint + tag based and domain-agnostic.
                    reflection_reason = "dependency_setup_repeat"
                    dependency_reflection = True
                    dependency_setup_reflections.add(error_fingerprint)
                elif error_fingerprint not in reflection_fingerprints and seen_error_fingerprints.count(error_fingerprint) >= 2:
                    reflection_reason = "repeat_fingerprint"
                    reflection_fingerprints.add(error_fingerprint)
                elif not reflection_threshold_triggered and hard_failure_count >= REFLECTION_ERROR_THRESHOLD:
                    reflection_reason = "error_threshold"
                    reflection_threshold_triggered = True

                if reflection_reason and not reflection_pending:
                    # Queue a reflection prompt for the next turn so the model
                    # explicitly diagnoses the failure before continuing.
                    reflection_pending = _build_reflection_prompt(
                        error_text=error_text,
                        fingerprint=error_fingerprint,
                        reason=reflection_reason,
                        include_dependency_fallback=dependency_reflection,
                    )
                    metrics["v2_reflection_prompts"] += 1
                    if dependency_reflection:
                        metrics["v2_dependency_fallback_checks"] += 1
                    metrics["v2_reflection_reasons"].append(
                        {
                            "step": step,
                            "fingerprint": error_fingerprint,
                            "reason": reflection_reason,
                        }
                    )

                v2_hints: list[str] = []
                v2_matches, conflict_losers = retrieve_on_error(
                    path=LESSONS_V2_PATH,
                    error_text=error_text,
                    fingerprint=error_fingerprint,
                    domain=domain,
                    task_id=task_id,
                    query_tags=error_tags,
                    max_results=2,
                    include_domainless=False,
                    enable_transfer=enable_transfer_retrieval,
                    transfer_policy=transfer_retrieval_policy,
                    transfer_max_results=transfer_retrieval_max_results,
                    transfer_score_weight=transfer_retrieval_score_weight,
                    unresolved_gaps=latest_unresolved_gaps,
                    candidate_policy=runtime_candidate_policy_effective,
                )
                for loser in conflict_losers:
                    contradiction_loser_counts[loser] += 1
                if v2_matches:
                    injected_lessons: list[dict[str, Any]] = []
                    retrieval_scores: list[dict[str, Any]] = []
                    lesson_lanes: dict[str, str] = {}
                    hint_lanes: dict[str, str] = {}
                    for match in v2_matches:
                        lesson_id = str(match.lesson.lesson_id)
                        # Placebo control keeps retrieval mechanics constant and
                        # only swaps lesson content for generic deterministic hints.
                        rule_text = (
                            _placebo_hint_for_lesson(lesson_id=lesson_id, task_id=task_id, domain=domain)
                            if benchmark_placebo
                            else str(match.lesson.rule_text)
                        )
                        lane = str(getattr(match, "lane", "strict")).strip().lower() or "strict"
                        v2_hints.append(rule_text)
                        injected_lessons.append(
                            {
                                "lesson_id": lesson_id,
                                "rule_text": rule_text,
                                "lane": lane,
                            }
                        )
                        retrieval_scores.append(
                            {
                                "lesson_id": lesson_id,
                                "lane": lane,
                                "lesson": {"lesson_id": lesson_id},
                                "score": {
                                    "score": float(match.score.score),
                                    "fingerprint_match": float(match.score.fingerprint_match),
                                    "tag_overlap": float(match.score.tag_overlap),
                                    "text_similarity": float(match.score.text_similarity),
                                    "reliability": float(match.score.reliability),
                                    "recency": float(match.score.recency),
                                },
                            }
                        )
                        lesson_lanes[lesson_id] = lane
                        hint_lanes[rule_text] = lane
                        if lane == "transfer":
                            metrics["v2_transfer_lane_activations"] += 1
                    lesson_activation_records.append(
                        {
                            "step": step,
                            "fingerprint": error_fingerprint,
                            "trigger": "on_error",
                            "lesson_ids": [match.lesson.lesson_id for match in v2_matches],
                            "lesson_lanes": lesson_lanes,
                            "placebo_applied": bool(benchmark_placebo),
                        }
                    )
                    memory_v2_payload = {
                        "on_error_injected_lessons": injected_lessons,
                        "injected_lesson_lanes": lesson_lanes,
                        "injected_hint_lanes": hint_lanes,
                        "retrieval_scores": retrieval_scores,
                    }
                    metrics["lesson_activations"] += len(v2_hints)
                    metrics["v2_lesson_activations"] += len(v2_hints)
                    if benchmark_placebo:
                        metrics["v2_lesson_activations_placebo"] += len(v2_hints)
                    else:
                        metrics["v2_lesson_activations_effective"] += len(v2_hints)

                # Legacy fallback keeps older runs usable while v2 memory warms up.
                legacy_hints: list[str] = []
                if not v2_hints and loaded_lesson_objects:
                    # Guard legacy fallback to the active task only. Legacy rows
                    # do not carry reliable domain metadata, so unrestricted
                    # cross-task matching can leak wrong-tool syntax hints.
                    legacy_candidates = [
                        lesson for lesson in loaded_lesson_objects
                        if str(getattr(lesson, "task_id", "")).strip() == task_id
                    ]
                    legacy_hints = find_lessons_for_error(
                        error_text,
                        legacy_candidates,
                        learning_mode=learning_mode,
                    )
                    if benchmark_placebo and legacy_hints:
                        legacy_hints = [
                            _placebo_hint_for_lesson(
                                lesson_id=f"legacy_hint:{idx}:{hint[:48]}",
                                task_id=task_id,
                                domain=domain,
                            )
                            for idx, hint in enumerate(legacy_hints)
                        ]
                    if legacy_hints:
                        metrics["lesson_activations"] += len(legacy_hints)

                merged_hints = v2_hints or legacy_hints
                if merged_hints:
                    hint_block = "\n\n--- HINT from prior sessions ---\n" + "\n".join(f"- {hint}" for hint in merged_hints)
                    result = ToolResult(error=(result.error or "") + hint_block)

            if result.is_error():
                metrics["tool_errors"] += 1

            event_payload = {
                "step": step,
                "tool": canonical_name,
                "tool_input": tool_input,
                "ok": not result.is_error(),
                "error": result.error,
                "output": result.output,
            }
            if memory_v2_payload:
                event_payload["memory_v2"] = memory_v2_payload
            write_event(paths.events_path, event_payload)

            if verbose:
                print(
                    f"[step {step:03d}] tool={canonical_name} ok={not result.is_error()} error={result.error!r}",
                    flush=True,
                )

            if on_step:
                on_step(step, canonical_name, not result.is_error(), result.error)

            tool_results.append(_tool_result_block(tool_use_id, result))

        if not tool_results:
            if _maybe_inject_contract_gap_retry(current_step=step, trigger="no_tool_call"):
                continue
            if verbose:
                print(f"[step {step:03d}] no tool call; model stopped.", flush=True)
            break
        messages.append({"role": "user", "content": tool_results})
        if retry_same_step and not saw_non_validation_tool_call:
            if verbose:
                print(
                    (
                        f"[step {step:03d}] validation retry "
                        f"{validation_retries_this_step}/{MAX_VALIDATION_RETRIES_PER_STEP}; repeating step."
                    ),
                    flush=True,
                )
            continue
        if step >= max_steps and _maybe_inject_contract_gap_retry(current_step=step, trigger="step_cap"):
            # Retry executes at the same logical step so the deterministic gap
            # close does not consume additional user-visible step budget.
            validation_retries_this_step = 0
            validation_retry_capped_this_step = False
            continue
        step += 1
        validation_retries_this_step = 0
        validation_retry_capped_this_step = False

    # --- Evaluation ---
    events = read_events(paths.events_path)
    probe_result = DeterministicProbeResult(
        source="none",
        applicable=False,
        passed=False,
        score=0.0,
        reasons=["no_verification_spec"],
        evidence={},
    )

    # Deterministic eval (CONTRACT.json) — works for domains that have contracts
    if has_contract:
        eval_events = _canonicalize_hotfix_transfer_eval_events(
            events=events,
            workspace=workspace,
            task_id=task_id,
        )
        # SQLite-style deterministic eval
        eval_result = evaluate_cli_session(
            task=task_text,
            task_id=task_id,
            events=eval_events,
            db_path=workspace.work_dir / "task.db",
            tasks_root=TASKS_ROOT,
        ).to_dict()
        probe_result = DeterministicProbeResult(
            source="CONTRACT.json",
            applicable=True,
            passed=bool(eval_result.get("passed", False)),
            score=float(eval_result.get("score", 0.0) or 0.0),
            reasons=list(eval_result.get("reasons", [])) if isinstance(eval_result.get("reasons"), list) else [],
            evidence=(
                dict(eval_result.get("evidence", {}))
                if isinstance(eval_result.get("evidence"), dict)
                else {}
            ),
        )
        metrics["eval_passed"] = probe_result.passed
        metrics["eval_score"] = probe_result.score
        metrics["eval_reasons"] = list(probe_result.reasons)
    else:
        verification_probe_spec = _verification_spec_for_probe(verification_spec)
        probe_result = _run_deterministic_probes(
            spec=verification_probe_spec,
            events=events,
            workspace=workspace,
        )
        if probe_result.applicable:
            # No-contract tasks become deterministic when local probes exist.
            eval_result = probe_result.to_eval_dict()
            metrics["eval_passed"] = probe_result.passed
            metrics["eval_score"] = probe_result.score
            metrics["eval_reasons"] = list(probe_result.reasons)
        else:
            eval_reasons = ["no_contract", "no_verification_spec"]
            if verification_spec_errors:
                eval_reasons.append("verification_spec_invalid")
            eval_result = {"passed": False, "score": 0.0, "reasons": eval_reasons}
            metrics["eval_passed"] = False
            metrics["eval_score"] = 0.0
            metrics["eval_reasons"] = list(eval_reasons)

    metrics["deterministic_probe_source"] = probe_result.source
    metrics["deterministic_probe_applicable"] = probe_result.applicable
    metrics["deterministic_probe_passed"] = probe_result.passed
    metrics["deterministic_probe_score"] = probe_result.score
    metrics["deterministic_probe_reasons"] = list(probe_result.reasons)
    metrics["deterministic_probe_evidence"] = dict(probe_result.evidence)
    final_unresolved_gaps = unresolved_contract_gaps(eval_result) if has_contract else []
    latest_unresolved_gaps = final_unresolved_gaps
    metrics["contract_gap_unresolved_count_final"] = int(len(final_unresolved_gaps))
    if contract_gap_prestop_artifacts:
        metrics["contract_gap_prestop_artifacts"] = list(contract_gap_prestop_artifacts)
    if has_contract and bool(contract_gap_retry) and contract_gap_retries_used > 0:
        postretry_artifact_path = paths.session_dir / "contract_gap_postretry.json"
        postretry_artifact_path.write_text(
            json.dumps(
                {
                    "retry_attempts_used": contract_gap_retries_used,
                    "eval_result": eval_result,
                    "unresolved_gaps": final_unresolved_gaps,
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        metrics["contract_gap_postretry_artifact"] = str(postretry_artifact_path)

    # LLM Judge can run in diagnostic mode even when deterministic contract passes.
    # Contract pass/fail remains authoritative whenever a contract exists.
    use_llm_judge = bool(judge_diagnostic) or (not metrics.get("eval_passed", False))
    if not has_contract:
        if llm_backend == "anthropic":
            # Keep judge telemetry on anthropic for no-contract runs even when
            # deterministic probes pass; probes remain primary signal.
            use_llm_judge = True
        elif not probe_result.applicable:
            # For non-anthropic transports, judge is only needed when probes are
            # unavailable and we have no deterministic signal.
            use_llm_judge = True
    metrics["judge_invoked"] = bool(use_llm_judge)
    if use_llm_judge:
        if client is None:
            raise RuntimeError("LLM judge requested but no LLM client is available.")
        final_state = adapter.capture_final_state(workspace)
        judge_docs_context = docs_judge_block

        def _judge_input_logger(payload: dict[str, Any]) -> None:
            nonlocal judge_input_bundle
            judge_input_bundle = _clone_json(payload)

        judge_result: JudgeResult = llm_judge(
            client=client,
            model=effective_judge_model,
            task_text=task_text,
            events=events,
            final_state=final_state,
            domain_name=domain,
            docs_context=judge_docs_context,
            temperature=runtime_temperature,
            input_logger=_judge_input_logger,
        )
        metrics["judge_passed"] = judge_result.passed
        metrics["judge_score"] = judge_result.score
        metrics["judge_reasons"] = judge_result.reasons
        metrics["judge_doc_grounding"] = list(judge_result.doc_grounding)
        metrics["judge_critique"] = judge_result.raw_response
        if probe_result.applicable:
            metrics["judge_fail_probe_pass"] = bool((not judge_result.passed) and probe_result.passed)
            metrics["judge_pass_probe_fail"] = bool(judge_result.passed and (not probe_result.passed))
        judge_payload_bundle = {
            "result": judge_result.to_dict(),
            "raw_response": judge_result.raw_response,
        }

        # Judge remains primary only when deterministic probes are unavailable.
        if not has_contract and not probe_result.applicable:
            metrics["eval_passed"] = judge_result.passed
            metrics["eval_score"] = judge_result.score
            metrics["eval_reasons"] = judge_result.reasons
            eval_result = judge_result.to_dict()

    # Deterministic low-confidence verifier stack.
    # This path is runtime-enforced (not prompt-based) and can override
    # judge-only outcomes when no contract exists.
    confidence_base = float(metrics.get("eval_score", 0.0) or 0.0)
    if not has_contract and metrics.get("judge_score") is not None:
        try:
            confidence_base = float(metrics.get("judge_score", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence_base = float(metrics.get("eval_score", 0.0) or 0.0)
    confidence_base = _clamp(confidence_base, 0.0, 1.0)
    metrics["verifier_confidence_base"] = round(confidence_base, 4)
    low_confidence_triggered = bool(verifier_stack_enabled) and confidence_base < float(low_confidence_threshold)
    metrics["verifier_low_confidence_triggered"] = bool(low_confidence_triggered)

    if low_confidence_triggered:
        probe_rows: list[dict[str, Any]] = []
        missing_verification_lines: list[str] = []

        required_verification_lines = _dedupe_nonempty_text_rows(
            [str(value) for value in (verification_spec.get("exact_output_lines", []) or [])]
        )
        if required_verification_lines and len(probe_rows) < max_low_confidence_probes:
            event_text = _collect_event_text_blobs(events)
            missing_verification_lines = [
                row for row in required_verification_lines
                if row not in event_text
            ]
            probe_rows.append(
                {
                    "probe_id": "verification_lines",
                    "applicable": True,
                    "passed": len(missing_verification_lines) == 0,
                    "detail": "matched" if not missing_verification_lines else "verification_line_missing",
                    "evidence": {
                        "required_lines": required_verification_lines,
                        "missing_lines": missing_verification_lines,
                    },
                }
            )

        required_files = _dedupe_nonempty_text_rows(
            [str(value) for value in (verification_spec.get("required_files", []) or [])]
        )
        if required_files and len(probe_rows) < max_low_confidence_probes:
            probe_rows.append(
                _run_required_files_probe(
                    work_dir=workspace.work_dir,
                    required_files=required_files,
                )
            )

        required_file_content_patterns = _normalize_required_file_content_patterns(
            verification_spec.get("required_file_content_patterns", [])
        )
        if required_file_content_patterns and len(probe_rows) < max_low_confidence_probes:
            probe_rows.append(
                _run_required_file_content_patterns_probe(
                    work_dir=workspace.work_dir,
                    required_file_content_patterns=required_file_content_patterns,
                )
            )

        required_queries = _normalize_required_queries(verification_spec.get("required_queries", []))
        if required_queries:
            default_query_db_path = _resolve_verification_db_path(
                work_dir=workspace.work_dir,
                db_path_hint=str(verification_spec.get("db_path", "")).strip(),
            )
            for query_spec in required_queries:
                if len(probe_rows) >= max_low_confidence_probes:
                    break
                query_db_path = _resolve_verification_db_path(
                    work_dir=workspace.work_dir,
                    db_path_hint=str(query_spec.get("db_path", "")).strip() or str(default_query_db_path),
                )
                probe_rows.append(
                    _run_required_query_probe(
                        db_path=query_db_path,
                        query_spec=query_spec,
                    )
                )

        if has_contract and len(probe_rows) < max_low_confidence_probes:
            no_unresolved_gaps = len(final_unresolved_gaps) == 0
            probe_rows.append(
                {
                    "probe_id": "contract_gap_count",
                    "applicable": True,
                    "passed": bool(no_unresolved_gaps),
                    "detail": "matched" if no_unresolved_gaps else "unresolved_contract_gaps",
                    "evidence": {
                        "unresolved_gap_count": len(final_unresolved_gaps),
                    },
                }
            )

        if domain == "sqlite":
            query_gaps = [
                row for row in final_unresolved_gaps
                if str(row.get("reason_code", "")).strip() == "required_query_mismatch"
                and str(row.get("query_sql", "")).strip()
            ]
            for gap in query_gaps:
                if len(probe_rows) >= max_low_confidence_probes:
                    break
                probe_rows.append(
                    _run_sqlite_gap_query_probe(
                        db_path=workspace.work_dir / "task.db",
                        gap=gap,
                    )
                )

        applicable = [row for row in probe_rows if bool(row.get("applicable", False))]
        if not applicable:
            probe_status = "inconclusive"
        elif any(not bool(row.get("passed", False)) for row in applicable):
            probe_status = "fail"
        elif all(bool(row.get("passed", False)) for row in applicable):
            probe_status = "pass"
        else:
            probe_status = "inconclusive"

        metrics["verifier_probe_status"] = probe_status
        metrics["verifier_probe_results"] = probe_rows
        metrics["verifier_probe_failures"] = sum(
            1 for row in applicable if not bool(row.get("passed", False))
        )

        override_applied = False
        failed_probe_reasons = sorted(
            {
                str(row.get("detail", "")).strip()
                for row in applicable
                if not bool(row.get("passed", False)) and str(row.get("detail", "")).strip()
            }
        )
        if probe_status == "fail" and not has_contract:
            merged_reasons = set(metrics.get("eval_reasons", []) or [])
            for reason in failed_probe_reasons:
                merged_reasons.add(f"deterministic_probe_failed:{reason}")
            metrics["eval_passed"] = False
            metrics["eval_score"] = round(min(float(metrics.get("eval_score", 0.0) or 0.0), 0.34), 3)
            metrics["eval_reasons"] = sorted(merged_reasons)
            if isinstance(eval_result, dict):
                eval_result["passed"] = False
                eval_result["score"] = float(metrics["eval_score"])
                eval_result["reasons"] = list(metrics["eval_reasons"])
            override_applied = True
        elif probe_status == "pass" and not has_contract:
            # Deterministic verifier probes are stronger than judge-only signal
            # for no-contract tasks. If all applicable probes pass, treat the
            # run as passed even when judge rationale is pessimistic.
            metrics["eval_passed"] = True
            metrics["eval_score"] = round(max(float(metrics.get("eval_score", 0.0) or 0.0), float(low_confidence_threshold)), 3)
            metrics["eval_reasons"] = ["deterministic_probe_passed"]
            if isinstance(eval_result, dict):
                eval_result["passed"] = True
                eval_result["score"] = float(metrics["eval_score"])
                eval_result["reasons"] = list(metrics["eval_reasons"])
            override_applied = True
        metrics["verifier_override_applied"] = bool(override_applied)

        if probe_status == "inconclusive" and bool(clarify_on_low_confidence):
            clarifying_question = _build_low_confidence_clarifying_question(
                task_id=task_id,
                missing_verification_lines=missing_verification_lines,
                unresolved_gaps=final_unresolved_gaps,
            )
            metrics["verifier_clarifying_question"] = clarifying_question
            write_event(
                paths.events_path,
                {
                    "step": int(metrics.get("steps", 0) or 0) + 1,
                    "tool": "verifier_clarify",
                    "tool_input": {
                        "confidence_base": confidence_base,
                        "threshold": low_confidence_threshold,
                    },
                    "ok": True,
                    "error": None,
                    "output": clarifying_question,
                },
            )

    # Evaluate watchdog policy before post-task patch hooks so safe mode can
    # disable risky self-edit/patch paths in the same run.
    hard_failure_counts = Counter(
        event.fingerprint for event in run_error_events if event.channel == "hard_failure"
    )
    repeated_error_signatures = sorted(
        fingerprint
        for fingerprint, count in hard_failure_counts.items()
        if count >= 2
    )
    loop_watchdog_snapshot = LoopWatchdogSnapshot(
        repeated_hard_failure_signatures=len(repeated_error_signatures),
        contract_gap_unresolved_count=len(final_unresolved_gaps),
        rejection_streak=int(loop_watchdog_state.rejection_streak),
    )
    loop_watchdog_decision = evaluate_watchdog_policy(
        state=loop_watchdog_state,
        snapshot=loop_watchdog_snapshot,
    )
    loop_watchdog_safe_mode_active = bool(loop_watchdog_decision.safe_mode_active)
    loop_watchdog_failure_signals = list(loop_watchdog_decision.failure_signals)
    loop_watchdog_stop_flag = bool(loop_watchdog_decision.stop_flag)
    metrics["loop_watchdog_safe_mode_active"] = bool(loop_watchdog_safe_mode_active)
    metrics["loop_watchdog_safe_mode_triggered"] = bool(loop_watchdog_decision.safe_mode_triggered)
    metrics["loop_watchdog_failure_signals"] = list(loop_watchdog_failure_signals)
    metrics["loop_watchdog_disable_self_edit"] = bool(loop_watchdog_decision.disable_self_edit)
    metrics["loop_watchdog_disable_posttask_patching"] = bool(loop_watchdog_decision.disable_posttask_patching)
    metrics["loop_watchdog_stop_flag"] = bool(loop_watchdog_stop_flag)
    metrics["loop_watchdog_repeated_hard_failure_signatures"] = int(loop_watchdog_snapshot.repeated_hard_failure_signatures)
    metrics["loop_watchdog_contract_gap_unresolved_count"] = int(loop_watchdog_snapshot.contract_gap_unresolved_count)
    metrics["loop_watchdog_safe_mode_failure_streak"] = int(loop_watchdog_decision.safe_mode_failure_streak)
    loop_watchdog_visibility_required = bool(loop_watchdog_safe_mode_active) and (
        bool(posttask_learn) or bool(self_edit_mode_active) or bool(loop_watchdog_stop_flag)
    )
    if loop_watchdog_visibility_required:
        write_event(
            paths.events_path,
            {
                "step": int(metrics.get("steps", 0) or 0) + 1,
                "tool": "loop_watchdog",
                "tool_input": {
                    "signal_counts": {
                        "repeated_hard_failure_signatures": int(loop_watchdog_snapshot.repeated_hard_failure_signatures),
                        "contract_gap_unresolved_count": int(loop_watchdog_snapshot.contract_gap_unresolved_count),
                        "rejection_streak": int(loop_watchdog_snapshot.rejection_streak),
                    },
                    "state_path": str(loop_watchdog_state_path),
                },
                "ok": not bool(loop_watchdog_stop_flag),
                "error": "watchdog_stop_flag" if bool(loop_watchdog_stop_flag) else None,
                "output": json.dumps(
                    {
                        "safe_mode_triggered": bool(loop_watchdog_decision.safe_mode_triggered),
                        "safe_mode_active": bool(loop_watchdog_decision.safe_mode_active),
                        "stop_flag": bool(loop_watchdog_decision.stop_flag),
                        "failure_signals": list(loop_watchdog_failure_signals),
                    },
                    ensure_ascii=True,
                ),
            },
        )
        if on_lifecycle_event is not None:
            try:
                on_lifecycle_event(
                    "step",
                    {
                        "step": int(metrics.get("steps", 0) or 0),
                        "trigger": "loop_watchdog_safe_mode",
                    },
                )
                if bool(loop_watchdog_stop_flag):
                    on_lifecycle_event(
                        "step",
                        {
                            "step": int(metrics.get("steps", 0) or 0),
                            "trigger": "loop_watchdog_stop_flag",
                        },
                    )
            except Exception:
                pass

    effective_self_edit_mode_active = bool(self_edit_mode_active) and not bool(loop_watchdog_decision.disable_self_edit)
    metrics["self_edit_mode_effective"] = bool(effective_self_edit_mode_active)
    if bool(self_edit_mode_active) and not bool(effective_self_edit_mode_active):
        append_self_edit_gate_event(
            sessions_root=SESSIONS_ROOT,
            run_id=run_id or "",
            session_id=session_id,
            task_id=task_id,
            domain=domain,
            learn_mode=learning_mode,
            stage="proposal",
            status="rejected",
            reason="loop_watchdog_safe_mode",
            metadata={
                "failure_signals": list(loop_watchdog_failure_signals),
            },
        )
        metrics["self_edit_gate_events"] = int(metrics.get("self_edit_gate_events", 0) or 0) + 1

    critic_no_updates = False

    if posttask_learn and skill_manifest_entries and client is not None:
        if client is None:
            raise RuntimeError("Posttask learning requires an LLM client.")
        # Demo mode keeps Memory V2 lesson generation/promotion active while
        # suppressing legacy skill patching hooks/events for cleaner demos.
        patching_enabled = architecture_mode == "full" and not memory_v2_demo_mode
        if bool(loop_watchdog_decision) and bool(loop_watchdog_decision.disable_posttask_patching):
            patching_enabled = False
            metrics["posttask_skill_patching_skipped_by_mode"] = True
            metrics["posttask_skill_patching_skip_reason"] = "loop_watchdog_safe_mode"
        metrics["posttask_patch_attempted"] = patching_enabled
        tail_events = [
            {
                "step": row.get("step"),
                "tool": row.get("tool"),
                "tool_input": row.get("tool_input"),
                "ok": row.get("ok"),
                "error": row.get("error"),
            }
            for row in events[-20:]
        ]
        routed_refs = [entry.skill_ref for entry in routed_entries]
        patch_manifest_entries = skill_manifest_entries
        patch_snapshot_refs = routed_refs
        if bool(effective_self_edit_mode_active) and self_edit_manifest_entries:
            patch_manifest_entries = list(self_edit_manifest_entries)
            patch_snapshot_refs = [entry.skill_ref for entry in patch_manifest_entries]
        skill_snapshots, skill_digests = _load_skill_snapshots(
            entries=patch_manifest_entries,
            routed_refs=patch_snapshot_refs,
        )
        domain_keywords = adapter.quality_keywords()
        critic_context = ""
        critic_context_sources: list[str] = []
        if learning_mode == "strict":
            # Strict-only critic retrieval path:
            # adapter exposes domain docs -> retrieval selects relevant chunks ->
            # critic prompt gets only those chunks as contextual grounding.
            retrieval_query = _build_critic_context_query(
                task_text=task_text,
                eval_result=eval_result,
                events_tail=tail_events,
            )
            if doc_mode != "none" and docs_bundle.selected_chunks:
                retrieved_chunks = docs_bundle.selected_chunks[:4]
            else:
                docs = adapter.docs_manifest()
                retrieved_chunks = knowledge_provider.retrieve(
                    query=retrieval_query,
                    docs=docs,
                    max_chunks=4,
                )
            critic_context = _format_critic_context(retrieved_chunks)
            critic_context_sources = [str(getattr(chunk, "source_id", "")) for chunk in retrieved_chunks]
        # Metrics always include provenance for observability/debugging, even
        # when strict mode yields no retrieved chunks.
        metrics["critic_context_sources"] = critic_context_sources
        lesson_model_for_run = model_executor if architecture_mode == "simplified" else critic_model_for_run
        lesson_result: LessonGenerationResult = generate_lessons(
            client=client,
            model=lesson_model_for_run,
            session_id=session_id,
            task_id=task_id,
            task=task_text,
            eval_result=eval_result,
            events_tail=tail_events,
            skill_refs_used=sorted(read_skill_refs),
            domain_name=domain,
            learning_mode=learning_mode,
            critic_context=critic_context,
            domain_keywords=domain_keywords,
            temperature=runtime_temperature,
        )
        metrics["critic_raw_lessons"] = [_serialize_lesson(lesson) for lesson in lesson_result.raw_lessons]
        metrics["critic_filtered_lessons"] = [_serialize_lesson(lesson) for lesson in lesson_result.filtered_lessons]
        filtered_texts = {lesson.lesson for lesson in lesson_result.filtered_lessons}
        rejected = [lesson for lesson in lesson_result.raw_lessons if lesson.lesson not in filtered_texts]
        metrics["critic_rejected_lessons"] = [_serialize_lesson(lesson) for lesson in rejected]
        metrics["lessons_generated"] = store_lessons(path=LESSONS_PATH, lessons=lesson_result.filtered_lessons)
        prune_lessons(LESSONS_PATH, max_per_task=20, domain_keywords=domain_keywords)

        # Memory V2 candidate generation uses executor self-reflection regardless
        # of architecture mode so utility can be measured against one generator.
        v2_reflection: LessonGenerationResult = generate_lessons(
            client=client,
            model=model_executor,
            session_id=session_id,
            task_id=task_id,
            task=task_text,
            eval_result=eval_result,
            events_tail=tail_events,
            skill_refs_used=sorted(read_skill_refs),
            domain_name=domain,
            learning_mode=learning_mode,
            critic_context=critic_context,
            domain_keywords=domain_keywords,
            temperature=runtime_temperature,
        )
        hard_events = [event for event in run_error_events if event.channel == "hard_failure"]
        fingerprint_counts = Counter(event.fingerprint for event in hard_events)
        recurring_fingerprints = [fingerprint for fingerprint, count in fingerprint_counts.items() if count >= 2]
        prioritized_fingerprints = recurring_fingerprints or [fingerprint for fingerprint, _ in fingerprint_counts.most_common(3)]
        if not repeated_error_signatures:
            repeated_error_signatures = list(recurring_fingerprints)
        v2_candidates: list[LessonRecord] = []
        structured_gap_rows = list(final_unresolved_gaps)
        fallback_rules: list[str] = []
        if structured_lessons_required and not v2_reflection.filtered_lessons and structured_gap_rows:
            fallback_rules = [_fallback_rule_for_gap(row) for row in structured_gap_rows[:3]]
            metrics["v2_structured_fallback_lessons"] = len(fallback_rules)
        source_lesson_texts = [lesson.lesson for lesson in v2_reflection.filtered_lessons] + fallback_rules
        for idx, lesson_text in enumerate(source_lesson_texts):
            gap_row = structured_gap_rows[min(idx, len(structured_gap_rows) - 1)] if structured_gap_rows else {}
            reason_code = str(gap_row.get("reason_code", "")).strip()
            gap_type = str(gap_row.get("gap_type", "")).strip()
            gap_signature = str(gap_row.get("gap_signature", "")).strip()
            if structured_lessons_required and (not reason_code or not gap_type):
                # Ensure structured rows remain machine-actionable.
                reason_code = str(metrics.get("eval_reasons", ["unknown_reason"])[0] if metrics.get("eval_reasons") else "unknown_reason")
                gap_type = "eval_reason"
                gap_signature = f"{reason_code}|eval_reason|{task_id}"
            tags = extract_tags(error=lesson_text)
            v2_candidates.append(
                LessonRecord.from_candidate(
                    session_id=session_id,
                    task_id=task_id,
                    task=task_text,
                    domain=domain,
                    rule_text=lesson_text,
                    trigger_fingerprints=prioritized_fingerprints,
                    tags=tags,
                    status="candidate",
                    reason_code=reason_code,
                    gap_type=gap_type,
                    gap_signature=gap_signature,
                )
            )
        v2_candidate_lessons = [
            {
                "lesson_id": row.lesson_id,
                "rule_text": row.rule_text,
                "trigger_fingerprints": list(row.trigger_fingerprints),
                "tags": list(row.tags),
                "reason_code": row.reason_code,
                "gap_type": row.gap_type,
                "gap_signature": row.gap_signature,
            }
            for row in v2_candidates
        ]
        posttask_lessons_raw = {
            "raw_lessons": [_serialize_lesson(lesson) for lesson in v2_reflection.raw_lessons],
            "filtered_lessons": [_serialize_lesson(lesson) for lesson in v2_reflection.filtered_lessons],
            "fallback_rules": list(fallback_rules),
            "unresolved_gaps": list(final_unresolved_gaps),
        }
        posttask_lessons_applied = {
            "candidates": v2_candidate_lessons,
            "structured_required": bool(structured_lessons_required),
        }
        posttask_lessons_raw_path = paths.session_dir / "posttask_lessons_raw.json"
        posttask_lessons_applied_path = paths.session_dir / "posttask_lessons_applied.json"
        posttask_lessons_raw_path.write_text(
            json.dumps(posttask_lessons_raw, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        posttask_lessons_applied_path.write_text(
            json.dumps(posttask_lessons_applied, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        metrics["posttask_lessons_raw_path"] = str(posttask_lessons_raw_path)
        metrics["posttask_lessons_applied_path"] = str(posttask_lessons_applied_path)
        v2_store_result = upsert_lesson_records(LESSONS_V2_PATH, v2_candidates)
        metrics["v2_lessons_generated"] = int(v2_store_result.get("inserted", 0))
        metrics["v2_lessons_merged"] = int(v2_store_result.get("merged", 0))
        metrics["v2_conflict_links"] = int(v2_store_result.get("conflict_links", 0))
        metrics["v2_fingerprint_counts"] = dict(fingerprint_counts)
        metrics["v2_fingerprint_recurrence"] = sum(1 for count in fingerprint_counts.values() if count > 1)
        metrics["v2_fingerprint_recurrence_before"] = metrics["v2_fingerprint_recurrence"]

        recent_scores = _load_recent_eval_scores(sessions_root=SESSIONS_ROOT, task_id=task_id, domain=domain)
        baseline_score = (sum(recent_scores) / float(len(recent_scores))) if recent_scores else None
        referee_gain = None if baseline_score is None else float(metrics.get("eval_score", 0.0) or 0.0) - baseline_score

        activations_by_lesson: dict[str, dict[str, float]] = defaultdict(lambda: {"error": 0.0, "eff": 0.0, "count": 0.0})
        helped = 0
        effective_activation_records = 0
        fingerprints_recur_after: set[str] = set()
        for activation in lesson_activation_records:
            if bool(activation.get("placebo_applied", False)):
                continue
            effective_activation_records += 1
            step_idx = int(activation.get("step", 0) or 0)
            fingerprint = str(activation.get("fingerprint", ""))
            repeats_after = sum(
                1
                for event in hard_events
                if event.fingerprint == fingerprint and int(event.metadata.get("step", 0) or 0) > step_idx
            )
            error_reduction = 1.0 if repeats_after == 0 else -_clamp(repeats_after / 3.0, 0.0, 1.0)
            step_efficiency_gain = _clamp(1.0 - (float(metrics.get("steps", 0) or 0) / float(max(1, max_steps))), -1.0, 1.0)
            if error_reduction > 0:
                helped += 1
            if repeats_after > 0:
                fingerprints_recur_after.add(fingerprint)
            for lesson_id in activation.get("lesson_ids", []):
                lesson_key = str(lesson_id).strip()
                if not lesson_key:
                    continue
                bucket = activations_by_lesson[lesson_key]
                bucket["error"] += error_reduction
                bucket["eff"] += step_efficiency_gain
                bucket["count"] += 1.0

        outcomes: list[LessonOutcome] = []
        current_records_by_id = {row.lesson_id: row for row in load_lesson_records(LESSONS_V2_PATH)}
        unresolved_reason_codes = {
            str(row.get("reason_code", "")).strip()
            for row in final_unresolved_gaps
            if str(row.get("reason_code", "")).strip()
        }
        unresolved_gap_signatures = {
            str(row.get("gap_signature", "")).strip()
            for row in final_unresolved_gaps
            if str(row.get("gap_signature", "")).strip()
        }
        for lesson_id, bucket in activations_by_lesson.items():
            count = max(1.0, bucket["count"])
            current_record = current_records_by_id.get(lesson_id)
            gap_resolved: bool | None = None
            if current_record is not None and (
                str(current_record.reason_code).strip() or str(current_record.gap_type).strip()
            ):
                candidate_signature = str(current_record.gap_signature).strip()
                candidate_reason = str(current_record.reason_code).strip()
                if candidate_signature and candidate_signature in unresolved_gap_signatures:
                    gap_resolved = False
                elif candidate_reason and candidate_reason in unresolved_reason_codes:
                    gap_resolved = False
                else:
                    gap_resolved = True
            outcomes.append(
                LessonOutcome(
                    lesson_id=lesson_id,
                    error_reduction=bucket["error"] / count,
                    step_efficiency_gain=bucket["eff"] / count,
                    referee_score_gain=referee_gain,
                    major_regression=bool(metrics.get("eval_score", 0.0) < 0.2 and metrics.get("tool_errors", 0) > 0),
                    contradiction_lost=False,
                    gap_resolved=gap_resolved,
                )
            )
        for lesson_id, count in contradiction_loser_counts.items():
            if benchmark_placebo:
                continue
            if count <= 0:
                continue
            outcomes.append(
                LessonOutcome(
                    lesson_id=lesson_id,
                    error_reduction=0.0,
                    step_efficiency_gain=0.0,
                    referee_score_gain=referee_gain,
                    contradiction_lost=True,
                    gap_resolved=False,
                )
            )
        records_before = {row.lesson_id: row.status for row in load_lesson_records(LESSONS_V2_PATH)}
        promotion_result_v2 = apply_outcomes(path=LESSONS_V2_PATH, outcomes=outcomes)
        records_after = {row.lesson_id: row.status for row in load_lesson_records(LESSONS_V2_PATH)}
        promoted_lesson_ids = sorted(
            lesson_id
            for lesson_id, status in records_after.items()
            if status == "promoted" and records_before.get(lesson_id) != "promoted"
        )
        suppressed_lesson_ids = sorted(
            lesson_id
            for lesson_id, status in records_after.items()
            if status == "suppressed" and records_before.get(lesson_id) != "suppressed"
        )
        metrics["v2_promoted"] = int(promotion_result_v2.get("promoted", 0))
        metrics["v2_suppressed"] = int(promotion_result_v2.get("suppressed", 0))
        metrics["v2_outcomes_updated"] = int(promotion_result_v2.get("updated", 0))
        metrics["v2_promoted_ids"] = promoted_lesson_ids
        metrics["v2_suppressed_ids"] = suppressed_lesson_ids
        metrics["v2_fingerprint_recurrence_after"] = len(fingerprints_recur_after)
        metrics["v2_retrieval_help_ratio"] = round(
            float(helped) / float(max(1, effective_activation_records)),
            4,
        )
        metrics["v2_retrieval_help_ratio_effective"] = metrics["v2_retrieval_help_ratio"]
        activation_by_step: dict[str, int] = {}
        activation_lane_counts: Counter[str] = Counter()
        activation_by_step_effective: dict[str, int] = {}
        activation_lane_counts_effective: Counter[str] = Counter()
        activation_records_effective = 0
        for activation in lesson_activation_records:
            step_key = str(int(activation.get("step", 0) or 0))
            lesson_ids = activation.get("lesson_ids", [])
            step_count = len(lesson_ids) if isinstance(lesson_ids, list) else 0
            activation_by_step[step_key] = activation_by_step.get(step_key, 0) + step_count
            lane_map = activation.get("lesson_lanes", {})
            if isinstance(lane_map, dict):
                for lane in lane_map.values():
                    lane_text = str(lane).strip().lower()
                    if lane_text:
                        activation_lane_counts[lane_text] += 1
            if bool(activation.get("placebo_applied", False)):
                continue
            activation_records_effective += 1
            activation_by_step_effective[step_key] = activation_by_step_effective.get(step_key, 0) + step_count
            if isinstance(lane_map, dict):
                for lane in lane_map.values():
                    lane_text = str(lane).strip().lower()
                    if lane_text:
                        activation_lane_counts_effective[lane_text] += 1
        metrics["v2_lesson_activations_by_step"] = activation_by_step
        metrics["v2_lesson_activations_by_step_effective"] = activation_by_step_effective
        metrics["v2_lesson_activations_per_run"] = len(lesson_activation_records)
        metrics["v2_lesson_activations_per_run_effective"] = activation_records_effective
        metrics["v2_lesson_activation_rate"] = round(
            float(metrics.get("v2_lesson_activations", 0) or 0) / float(max(1, int(metrics.get("steps", 0) or 0))),
            4,
        )
        metrics["v2_lesson_activation_lane_counts"] = dict(activation_lane_counts)
        metrics["v2_lesson_activation_lane_counts_effective"] = dict(activation_lane_counts_effective)

        # Simplified architecture stores lessons only and skips post-task skill patches.
        if not patching_enabled:
            metrics["posttask_skill_patching_skipped_by_mode"] = True
            if not metrics.get("posttask_skill_patching_skip_reason"):
                if memory_v2_demo_mode:
                    metrics["posttask_skill_patching_skip_reason"] = "memory_v2_demo_mode"
                else:
                    metrics["posttask_skill_patching_skip_reason"] = "architecture_mode"
        else:
            proposed_updates, confidence, reflection_raw = propose_skill_updates(
                client=client,
                model=critic_model_for_run,
                task=task_text,
                metrics=metrics,
                eval_result=eval_result,
                events_tail=tail_events,
                routed_skill_refs=routed_refs,
                read_skill_refs=sorted(read_skill_refs),
                skill_snapshots=skill_snapshots,
                domain_name=adapter.name,
            )
            if not proposed_updates:
                parse_rejection_counts = {
                    "parse_fail": 0,
                    "required_digest_mismatch": 0,
                    "duplicate_jaccard": 0,
                    "replace_miss": 0,
                }
                parsed_updates, parsed_confidence = parse_reflection_response(
                    reflection_raw,
                    rejection_counts=parse_rejection_counts,
                )
                if parsed_updates:
                    proposed_updates = parsed_updates
                    confidence = parsed_confidence
                for reason, count in parse_rejection_counts.items():
                    metrics["posttask_rejection_counts"][reason] = int(
                        metrics["posttask_rejection_counts"].get(reason, 0)
                    ) + int(count)

            critic_no_updates = len(proposed_updates) == 0
            required_digests = {update.skill_ref: update.skill_digest for update in proposed_updates}
            if bool(effective_self_edit_mode_active):
                allowed_refs = self_edit_allowed_refs()
            else:
                allowed_refs = {update.skill_ref for update in proposed_updates}

            if bool(effective_self_edit_mode_active):
                proposal_status = "proposed" if proposed_updates else "rejected"
                proposal_reason = None if proposed_updates else "no_updates"
                append_self_edit_gate_event(
                    sessions_root=SESSIONS_ROOT,
                    run_id=run_id or "",
                    session_id=session_id,
                    task_id=task_id,
                    domain=domain,
                    learn_mode=learning_mode,
                    stage="proposal",
                    status=proposal_status,
                    reason=proposal_reason,
                    metadata={
                        "confidence": float(confidence),
                        "update_count": int(len(proposed_updates)),
                    },
                )
                metrics["self_edit_gate_events"] = int(metrics.get("self_edit_gate_events", 0) or 0) + 1

            effective_posttask_mode = posttask_mode
            if bool(effective_self_edit_mode_active) and posttask_mode != "direct":
                effective_posttask_mode = "direct"
                metrics["self_edit_forced_direct_mode"] = True

            if bool(effective_self_edit_mode_active):
                patch_result = apply_guarded_self_edit_updates(
                    entries=patch_manifest_entries,
                    updates=proposed_updates,
                    confidence=confidence,
                    track_root=TRACK_ROOT,
                    required_skill_digests=required_digests,
                    allowed_skill_refs=allowed_refs,
                )
                metrics["posttask_patch_applied"] = int(patch_result.get("applied", 0))
                patch_rejections = patch_result.get("rejection_counts", {})
                if isinstance(patch_rejections, dict):
                    for reason, count in patch_rejections.items():
                        reason_key = str(reason)
                        metrics["posttask_rejection_counts"][reason_key] = int(
                            metrics["posttask_rejection_counts"].get(reason_key, 0)
                        ) + int(count)
                patch_status = "accepted" if int(patch_result.get("applied", 0) or 0) > 0 else "rejected"
                append_self_edit_gate_event(
                    sessions_root=SESSIONS_ROOT,
                    run_id=run_id or "",
                    session_id=session_id,
                    task_id=task_id,
                    domain=domain,
                    learn_mode=learning_mode,
                    stage="patch",
                    status=patch_status,
                    reason=str(patch_result.get("skipped_reason", "")).strip() or None,
                    rollback_reason="verification_failed" if bool(patch_result.get("rolled_back", False)) else None,
                    metadata={
                        "applied": int(patch_result.get("applied", 0) or 0),
                        "updated_skill_refs": list(patch_result.get("updated_skill_refs", [])),
                    },
                )
                metrics["self_edit_gate_events"] = int(metrics.get("self_edit_gate_events", 0) or 0) + 1
            elif effective_posttask_mode == "direct":
                patch_result = apply_skill_updates(
                    entries=skill_manifest_entries,
                    updates=proposed_updates,
                    confidence=confidence,
                    skills_root=SKILLS_ROOT,
                    manifest_path=MANIFEST_PATH,
                    required_skill_digests=required_digests,
                    allowed_skill_refs=allowed_refs,
                )
                metrics["posttask_patch_applied"] = int(patch_result.get("applied", 0))
                patch_rejections = patch_result.get("rejection_counts", {})
                if isinstance(patch_rejections, dict):
                    for reason, count in patch_rejections.items():
                        reason_key = str(reason)
                        metrics["posttask_rejection_counts"][reason_key] = int(
                            metrics["posttask_rejection_counts"].get(reason_key, 0)
                        ) + int(count)
            else:
                patch_result = queue_skill_update_candidates(
                    queue_path=QUEUE_PATH,
                    updates=proposed_updates,
                    confidence=confidence,
                    session_id=session_id,
                    task_id=task_id,
                    required_skill_digests=required_digests,
                    allowed_skill_refs=allowed_refs,
                    evaluation=eval_result,
                )
                metrics["posttask_candidates_queued"] = int(patch_result.get("queued", 0))
                queue_rejections = patch_result.get("rejection_counts", {})
                if isinstance(queue_rejections, dict):
                    for reason, count in queue_rejections.items():
                        reason_key = str(reason)
                        metrics["posttask_rejection_counts"][reason_key] = int(
                            metrics["posttask_rejection_counts"].get(reason_key, 0)
                        ) + int(count)

            write_event(
                paths.events_path,
                {
                    "step": int(metrics["steps"]) + 1,
                    "tool": "posttask_hook",
                    "tool_input": {"mode": effective_posttask_mode, "critic_model": critic_model_for_run},
                    "ok": True,
                    "error": None,
                    "output": json.dumps(
                        {
                            "confidence": confidence,
                            "update_count": len(proposed_updates),
                            "result": patch_result,
                        },
                        ensure_ascii=True,
                    ),
                },
            )

            if bool(effective_self_edit_mode_active):
                promotion_result = {
                    "attempted": False,
                    "applied": 0,
                    "reason": "self_edit_direct_mode",
                }
                append_self_edit_gate_event(
                    sessions_root=SESSIONS_ROOT,
                    run_id=run_id or "",
                    session_id=session_id,
                    task_id=task_id,
                    domain=domain,
                    learn_mode=learning_mode,
                    stage="promotion",
                    status="rejected",
                    reason="self_edit_direct_mode",
                    metadata={"posttask_mode": str(posttask_mode)},
                )
                metrics["self_edit_gate_events"] = int(metrics.get("self_edit_gate_events", 0) or 0) + 1
            else:
                promotion_result = auto_promote_queued_candidates(
                    entries=skill_manifest_entries,
                    queue_path=QUEUE_PATH,
                    promoted_path=PROMOTED_PATH,
                    sessions_root=SESSIONS_ROOT,
                    task_id=task_id,
                    skills_root=SKILLS_ROOT,
                    manifest_path=MANIFEST_PATH,
                    min_runs=promotion_min_runs,
                    min_delta=promotion_min_delta,
                    max_regressions=promotion_max_regressions,
                )
            metrics["auto_promotion_applied"] = int(promotion_result.get("applied", 0))
            metrics["auto_promotion_reason"] = promotion_result.get("reason")
            write_event(
                paths.events_path,
                {
                    "step": int(metrics["steps"]) + 2,
                    "tool": "promotion_gate",
                    "tool_input": {"task_id": task_id, "min_runs": promotion_min_runs, "min_delta": promotion_min_delta},
                    "ok": True,
                    "error": None,
                    "output": json.dumps(promotion_result, ensure_ascii=True),
                },
            )
    elif posttask_learn and client is None:
        metrics["posttask_skill_patching_skipped_by_mode"] = True
        metrics["posttask_skill_patching_skip_reason"] = "no_llm_client"

    loop_watchdog_posttask_rejection_total = _sum_rejection_counts(metrics.get("posttask_rejection_counts", {}))
    metrics["loop_watchdog_posttask_rejection_total"] = int(loop_watchdog_posttask_rejection_total)
    if loop_watchdog_decision is None:
        loop_watchdog_decision = LoopWatchdogDecision(
            safe_mode_active=False,
            safe_mode_triggered=False,
            stop_flag=False,
            failure_signals=(),
            disable_self_edit=False,
            disable_posttask_patching=False,
            safe_mode_failure_streak=0,
        )
    loop_watchdog_state = next_watchdog_state(
        state=loop_watchdog_state,
        decision=loop_watchdog_decision,
        run_id=str(run_id or ""),
        posttask_rejection_total=loop_watchdog_posttask_rejection_total,
    )
    metrics["loop_watchdog_rejection_streak_final"] = int(loop_watchdog_state.rejection_streak)
    metrics["loop_watchdog_safe_mode_active"] = bool(loop_watchdog_decision.safe_mode_active)
    metrics["loop_watchdog_stop_flag"] = bool(loop_watchdog_decision.stop_flag)
    metrics["loop_watchdog_safe_mode_failure_streak"] = int(loop_watchdog_state.safe_mode_failure_streak)
    try:
        persist_watchdog_state(state_path=loop_watchdog_state_path, state=loop_watchdog_state)
        metrics["loop_watchdog_state_persisted"] = True
    except Exception:
        metrics["loop_watchdog_state_persisted"] = False

    escalation_state = _escalate_if_needed(
        state=escalation_state,
        base_model=model_critic,
        auto_escalate=auto_escalate_critic,
        eval_score=float(metrics["eval_score"]),
        eval_passed=bool(metrics["eval_passed"]),
        critic_no_updates=critic_no_updates,
        score_threshold=escalation_score_threshold,
        consecutive_runs=max(1, escalation_consecutive_runs),
    )
    _save_escalation_state(escalation_state)

    metrics["critic_no_updates_streak"] = int(escalation_state.get("critic_no_updates_streak", 0))
    metrics["low_score_streak"] = int(escalation_state.get("low_score_streak", 0))
    metrics["escalation_state"] = {
        "tier": escalation_state.get("tier"),
        "override_runs_remaining": escalation_state.get("override_runs_remaining"),
        "last_trigger": escalation_state.get("last_trigger"),
        "auto_escalate_critic": auto_escalate_critic,
    }
    if not repeated_error_signatures:
        hard_failure_counts = Counter(
            event.fingerprint for event in run_error_events if event.channel == "hard_failure"
        )
        repeated_error_signatures = [
            fingerprint
            for fingerprint, count in hard_failure_counts.items()
            if count >= 2
        ]
    metrics["repeated_error_signatures"] = sorted(set(repeated_error_signatures))
    metrics["elapsed_s"] = round(time.time() - float(metrics["time_start"]), 3)

    docs_artifacts_path = write_doc_artifacts(session_dir=paths.session_dir, bundle=docs_bundle)
    learning_artifacts = {
        "contract_gap_retry": {
            "enabled": bool(contract_gap_retry),
            "steps_budget": int(contract_gap_retry_steps),
            "attempts": int(metrics.get("contract_gap_retry_attempts", 0) or 0),
            "triggered": int(metrics.get("contract_gap_retry_triggered", 0) or 0),
            "closure_checks": int(metrics.get("contract_closure_checks", 0) or 0),
            "closure_check_failures": int(metrics.get("contract_closure_check_failures", 0) or 0),
            "closure_check_last_status": str(metrics.get("contract_closure_check_last_status", "not_run")),
            "closure_check_last_missing": list(metrics.get("contract_closure_check_last_missing", [])),
            "prestop_artifacts": list(metrics.get("contract_gap_prestop_artifacts", [])),
            "postretry_artifact": metrics.get("contract_gap_postretry_artifact"),
            "unresolved_count_prestop": int(metrics.get("contract_gap_unresolved_count_prestop", 0) or 0),
            "unresolved_count_final": int(metrics.get("contract_gap_unresolved_count_final", 0) or 0),
            "unresolved_gaps_final": list(final_unresolved_gaps),
        },
        "loop_watchdog": {
            "state_path": str(loop_watchdog_state_path),
            "safe_mode_initial": bool(metrics.get("loop_watchdog_safe_mode_initial", False)),
            "safe_mode_active": bool(metrics.get("loop_watchdog_safe_mode_active", False)),
            "safe_mode_triggered": bool(metrics.get("loop_watchdog_safe_mode_triggered", False)),
            "stop_flag": bool(metrics.get("loop_watchdog_stop_flag", False)),
            "failure_signals": list(metrics.get("loop_watchdog_failure_signals", [])),
            "repeated_hard_failure_signatures": int(
                metrics.get("loop_watchdog_repeated_hard_failure_signatures", 0) or 0
            ),
            "contract_gap_unresolved_count": int(
                metrics.get("loop_watchdog_contract_gap_unresolved_count", 0) or 0
            ),
            "rejection_streak_initial": int(metrics.get("loop_watchdog_rejection_streak_initial", 0) or 0),
            "rejection_streak_final": int(metrics.get("loop_watchdog_rejection_streak_final", 0) or 0),
            "safe_mode_failure_streak": int(metrics.get("loop_watchdog_safe_mode_failure_streak", 0) or 0),
            "posttask_rejection_total": int(metrics.get("loop_watchdog_posttask_rejection_total", 0) or 0),
        },
        "lesson_candidates": v2_candidate_lessons,
        "promoted_lessons": promoted_lesson_ids,
        "suppressed_lessons": suppressed_lesson_ids,
        "repeated_error_signatures": sorted(set(repeated_error_signatures)),
        "posttask_rejection_counts": dict(metrics.get("posttask_rejection_counts", {})),
        "lesson_activations_by_step": dict(metrics.get("v2_lesson_activations_by_step", {})),
        "judge": {
            "invoked": bool(metrics.get("judge_invoked", False)),
            "diagnostic_mode": bool(metrics.get("judge_diagnostic", False)),
            "reasons": list(metrics.get("judge_reasons", [])),
            "doc_grounding": list(metrics.get("judge_doc_grounding", [])),
            "critique": str(metrics.get("judge_critique", "")),
        },
        "verifier_stack": {
            "enabled": bool(metrics.get("verifier_stack_enabled", False)),
            "confidence_base": metrics.get("verifier_confidence_base"),
            "low_confidence_threshold": metrics.get("verifier_low_confidence_threshold"),
            "low_confidence_triggered": bool(metrics.get("verifier_low_confidence_triggered", False)),
            "probe_status": str(metrics.get("verifier_probe_status", "not_run")),
            "probe_failures": int(metrics.get("verifier_probe_failures", 0) or 0),
            "override_applied": bool(metrics.get("verifier_override_applied", False)),
            "clarifying_question": str(metrics.get("verifier_clarifying_question", "")),
            "probe_results": list(metrics.get("verifier_probe_results", [])),
        },
        "metrics_summary": {
            "eval_passed": bool(metrics.get("eval_passed", False)),
            "eval_score": float(metrics.get("eval_score", 0.0) or 0.0),
            "steps": int(metrics.get("steps", 0) or 0),
            "tool_errors": int(metrics.get("tool_errors", 0) or 0),
            "lessons_loaded": int(metrics.get("lessons_loaded", 0) or 0),
            "v2_lessons_generated": int(metrics.get("v2_lessons_generated", 0) or 0),
            "v2_lesson_activations": int(metrics.get("v2_lesson_activations", 0) or 0),
        },
    }
    learning_artifacts_path = paths.session_dir / "learning_artifacts.json"
    learning_artifacts_path.write_text(
        json.dumps(learning_artifacts, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    metrics["docs_artifacts_path"] = str(docs_artifacts_path)
    metrics["learning_artifacts_path"] = str(learning_artifacts_path)
    prompt_artifacts = {
        "executor": {
            "system_prompt": system_prompt,
            "task_payload": {"role": "user", "content": [{"type": "text", "text": task_text}]},
            "docs_context": docs_executor_block,
            "selected_lessons": {
                "lessons_text": lessons_text,
                "v2_prerun_lesson_ids": list(prerun_v2_ids),
            },
            "skills": {
                "routed_refs": list(routed_refs),
                "required_skill_refs": sorted(required_skill_refs),
                "routed_entries": [
                    {
                        "skill_ref": entry.skill_ref,
                        "title": entry.title,
                        "description": entry.description,
                        "version": entry.version,
                        "path": entry.path,
                    }
                    for entry in routed_entries
                ],
            },
            "tools": _clone_json(tools),
            "calls": executor_input_bundles,
        },
        "judge": {
            "invoked": bool(metrics.get("judge_invoked", False)),
            "diagnostic_mode": bool(metrics.get("judge_diagnostic", False)),
            "model": effective_judge_model,
            "docs_context": docs_judge_block,
            "input_bundle": judge_input_bundle,
            "result_bundle": judge_payload_bundle,
        },
        "docs": {
            "selected_source_ids": docs_selected_source_ids,
            "docs_mode": doc_mode,
            "docs_retrieval_mode": doc_retrieval,
        },
    }
    prompt_artifacts_path = paths.session_dir / "prompt_artifacts.json"
    prompt_artifacts_path.write_text(
        json.dumps(prompt_artifacts, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    metrics["prompt_artifacts_path"] = str(prompt_artifacts_path)

    write_metrics(paths.metrics_path, metrics)
    return CliRunResult(
        messages=messages,
        metrics=metrics,
        task_text=task_text,
        system_prompt=system_prompt,
        lessons_text=lessons_text,
        tools=tools,
    )
