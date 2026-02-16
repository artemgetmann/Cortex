from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import anthropic

from config import CortexConfig
from tracks.cli_sqlite.domain_adapter import DomainAdapter, DomainWorkspace, ToolResult
from tracks.cli_sqlite.eval_cli import evaluate_cli_session
from tracks.cli_sqlite.judge_llm import JudgeResult, default_judge_model, llm_judge
from tracks.cli_sqlite.knowledge_provider import LocalDocsKnowledgeProvider
from tracks.cli_sqlite.error_capture import ErrorEvent, build_error_fingerprint, extract_tags
from tracks.cli_sqlite.lesson_promotion_v2 import LessonOutcome, apply_outcomes
from tracks.cli_sqlite.lesson_retrieval_v2 import (
    DEFAULT_TRANSFER_MAX_RESULTS,
    DEFAULT_TRANSFER_SCORE_COEFFICIENT,
    retrieve_on_error,
    retrieve_pre_run,
)
from tracks.cli_sqlite.lesson_store_v2 import LessonRecord, migrate_legacy_lessons, upsert_lesson_records
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
READ_SKILL_TOOL_NAME = "read_skill"
SHOW_FIXTURE_TOOL_NAME = "show_fixture"
LEARNING_MODES = ("strict", "legacy")
DEFAULT_LEARNING_MODE = "legacy"
ARCHITECTURE_MODES = ("full", "simplified")
DEFAULT_ARCHITECTURE_MODE = "full"
DEFAULT_TRANSFER_RETRIEVAL_MAX_RESULTS = DEFAULT_TRANSFER_MAX_RESULTS
DEFAULT_TRANSFER_RETRIEVAL_SCORE_WEIGHT = DEFAULT_TRANSFER_SCORE_COEFFICIENT


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


def _load_task_text(tasks_root: Path, task_id: str) -> str:
    """Load task description from task.md file, with fallback."""
    task_md = tasks_root / task_id / "task.md"
    if task_md.exists():
        return task_md.read_text(encoding="utf-8").strip()
    return f"Task: {task_id}. Complete using available tools."


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


def _clip_text(text: str, *, max_chars: int = 4000) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


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


def _format_v2_lesson_block(matches: list[Any]) -> tuple[str, list[str]]:
    if not matches:
        return "", []
    lines = ["Memory V2 lessons (high-signal):"]
    lesson_ids: list[str] = []
    for match in matches:
        lesson = getattr(match, "lesson", None)
        score = getattr(match, "score", None)
        if lesson is None:
            continue
        lesson_ids.append(str(getattr(lesson, "lesson_id", "")))
        score_value = float(getattr(score, "score", 0.0) or 0.0) if score is not None else 0.0
        lines.append(f"- ({score_value:.2f}) {lesson.rule_text}")
    return "\n".join(lines), [value for value in lesson_ids if value]


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


def _is_skill_gate_satisfied(
    *,
    read_skill_refs: set[str],
    required_skill_refs: set[str],
) -> bool:
    if not required_skill_refs:
        return True
    return bool(read_skill_refs & required_skill_refs)


def _resolve_adapter(domain: str, *, cryptic_errors: bool = False, semi_helpful_errors: bool = False) -> DomainAdapter:
    """Resolve a domain name to its adapter instance."""
    if domain == "sqlite":
        from tracks.cli_sqlite.domains.sqlite_adapter import SqliteAdapter
        return SqliteAdapter()
    if domain == "gridtool":
        from tracks.cli_sqlite.domains.gridtool_adapter import GridtoolAdapter
        return GridtoolAdapter(
            cryptic_errors=cryptic_errors,
            semi_helpful_errors=semi_helpful_errors,
            mixed_errors=False,
        )
    if domain == "fluxtool":
        from tracks.cli_sqlite.domains.fluxtool_adapter import FluxtoolAdapter
        return FluxtoolAdapter(
            cryptic_errors=cryptic_errors,
            semi_helpful_errors=semi_helpful_errors,
            mixed_errors=False,
        )
    if domain == "artic":
        from tracks.cli_sqlite.domains.artic_adapter import ArticAdapter
        return ArticAdapter()
    raise ValueError(f"Unknown domain: {domain!r}. Available: sqlite, gridtool, fluxtool, artic")


def _resolve_adapter_with_mode(
    domain: str,
    *,
    cryptic_errors: bool,
    semi_helpful_errors: bool,
    mixed_errors: bool,
) -> DomainAdapter:
    """Resolve adapter with optional mixed per-command error policy."""
    if domain == "gridtool":
        from tracks.cli_sqlite.domains.gridtool_adapter import GridtoolAdapter
        return GridtoolAdapter(
            cryptic_errors=cryptic_errors,
            semi_helpful_errors=semi_helpful_errors,
            mixed_errors=mixed_errors,
        )
    if domain == "fluxtool":
        from tracks.cli_sqlite.domains.fluxtool_adapter import FluxtoolAdapter
        return FluxtoolAdapter(
            cryptic_errors=cryptic_errors,
            semi_helpful_errors=semi_helpful_errors,
            mixed_errors=mixed_errors,
        )
    return _resolve_adapter(domain, cryptic_errors=cryptic_errors, semi_helpful_errors=semi_helpful_errors)


def _serialize_lesson(lesson: Any) -> dict[str, Any]:
    return {
        "category": getattr(lesson, "category", ""),
        "lesson": getattr(lesson, "lesson", ""),
        "evidence_steps": getattr(lesson, "evidence_steps", []),
        "eval_score": getattr(lesson, "eval_score", 0.0),
        "eval_passed": getattr(lesson, "eval_passed", False),
    }


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
        required_skill_refs = set(routed_refs[:1]) if require_skill_read else set()
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
        max_results=6,
    )
    v2_block, _ = _format_v2_lesson_block(v2_matches)
    if v2_block:
        lessons_text = f"{lessons_text}\n\n{v2_block}".strip()
    domain_fragment = adapter.system_prompt_fragment()
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
    on_step: Callable[[int, str, bool, str | None], Any] | None = None,
) -> CliRunResult:
    learning_mode = _normalize_learning_mode(learning_mode)
    architecture_mode = _normalize_architecture_mode(architecture_mode)
    # Local retrieval provider is intentionally lightweight and deterministic.
    # Strict mode uses it for critic context; legacy ignores it.
    knowledge_provider = LocalDocsKnowledgeProvider()
    transfer_retrieval_max_results = max(0, int(transfer_retrieval_max_results))
    transfer_retrieval_score_weight = max(0.0, float(transfer_retrieval_score_weight))
    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key, max_retries=3)
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

    # Build full manifest always (needed for posttask learning even in bootstrap)
    skill_manifest_entries = build_skill_manifest(skills_root=SKILLS_ROOT, manifest_path=MANIFEST_PATH)

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
        required_skill_refs = set(routed_refs[:1]) if require_skill_read else set()
        skills_text = manifest_summaries_text(routed_entries)
    domain_keywords = adapter.quality_keywords()
    lessons_text, lessons_loaded = load_relevant_lessons(
        path=LESSONS_PATH,
        task_id=task_id,
        task=task_text,
        max_lessons=12,
        max_sessions=8,
        domain_keywords=domain_keywords,
    )
    # Keep V2 backward-compatible with legacy lessons by migrating legacy rows
    # into the v2 store before retrieval. The migration is idempotent.
    migrate_legacy_lessons(legacy_path=LESSONS_PATH, v2_path=LESSONS_V2_PATH)
    prerun_v2_matches, _ = retrieve_pre_run(
        path=LESSONS_V2_PATH,
        task_id=task_id,
        domain=domain,
        task_text=task_text,
        max_results=8,
    )
    prerun_v2_block, prerun_v2_ids = _format_v2_lesson_block(prerun_v2_matches)
    if prerun_v2_block:
        lessons_text = f"{lessons_text}\n\n{prerun_v2_block}".strip()
    # Load lesson objects for error-triggered injection during the run
    loaded_lesson_objects = load_lesson_objects(
        path=LESSONS_PATH,
        task_id=task_id,
        domain_keywords=domain_keywords,
    )

    domain_fragment = adapter.system_prompt_fragment()
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
    else:
        effective_judge_model = model_judge or default_judge_model(model_executor)

    metrics: dict[str, Any] = {
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
        "skill_gate_blocks": 0,
        "skill_reads": 0,
        "required_skill_refs": sorted(required_skill_refs),
        "require_skill_read": require_skill_read,
        "lessons_loaded": lessons_loaded,
        "v2_lessons_loaded": len(prerun_v2_ids),
        "v2_prerun_lesson_ids": prerun_v2_ids,
        "lesson_activations": 0,
        "v2_lesson_activations": 0,
        "v2_error_events": 0,
        "v2_retrieval_help_ratio": 0.0,
        "v2_transfer_retrieval_enabled": bool(enable_transfer_retrieval),
        "v2_transfer_retrieval_max_results": transfer_retrieval_max_results,
        "v2_transfer_retrieval_score_weight": transfer_retrieval_score_weight,
        "v2_transfer_lane_activations": 0,
        "v2_promoted": 0,
        "v2_suppressed": 0,
        "v2_fingerprint_recurrence_before": 0,
        "v2_fingerprint_recurrence_after": 0,
        "lessons_generated": 0,
        "v2_lessons_generated": 0,
        "posttask_patch_attempted": False,
        "posttask_skill_patching_skipped_by_mode": False,
        "posttask_skill_patching_skip_reason": None,
        "posttask_candidates_queued": 0,
        "posttask_patch_applied": 0,
        "auto_promotion_applied": 0,
        "auto_promotion_reason": None,
        "memory_v2_demo_mode": bool(memory_v2_demo_mode),
        "executor_model": model_executor,
        "critic_model": critic_model_for_run,
        "judge_model": effective_judge_model,
        "eval_score": 0.0,
        "eval_reasons": [],
        "eval_passed": False,
        "judge_score": None,
        "judge_passed": None,
        "judge_reasons": [],
        "judge_critique": "",
        "critic_raw_lessons": [],
        "critic_filtered_lessons": [],
        "critic_rejected_lessons": [],
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
    lesson_activation_records: list[dict[str, Any]] = []
    contradiction_loser_counts: dict[str, int] = defaultdict(int)

    for step in range(1, max_steps + 1):
        metrics["steps"] = step
        response = client.messages.create(
            model=model_executor,
            max_tokens=1800,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )

        try:
            usage = response.usage.model_dump()  # type: ignore[attr-defined]
        except Exception:
            usage_obj = getattr(response, "usage", None)
            usage = usage_obj.model_dump() if usage_obj is not None and hasattr(usage_obj, "model_dump") else {}
        metrics["usage"].append(usage)

        assistant_blocks = [block.model_dump() for block in response.content]  # type: ignore[attr-defined]
        messages.append({"role": "assistant", "content": assistant_blocks})
        tool_results: list[dict[str, Any]] = []

        for block in assistant_blocks:
            if not (isinstance(block, dict) and block.get("type") == "tool_use"):
                continue
            tool_name_raw = str(block.get("name", ""))
            canonical_name = alias_map.get(tool_name_raw, tool_name_raw)
            tool_use_id = str(block.get("id", ""))
            tool_input = block.get("input", {})
            tool_input = tool_input if isinstance(tool_input, dict) else {}
            metrics["tool_actions"] += 1
            memory_v2_payload: dict[str, Any] = {}

            if canonical_name == READ_SKILL_TOOL_NAME:
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

            # Memory V2 capture + retrieval path:
            # - capture failure events via universal channels
            # - fetch fingerprint-aligned hints in the same run
            # - fallback to legacy lesson matcher if V2 has no signal yet
            if result.is_error() and canonical_name == executor_tool_name:
                error_text = result.error or ""
                action_state = {
                    "tool": canonical_name,
                    "tool_input": tool_input,
                    "step": step,
                    "task_id": task_id,
                    "domain": domain,
                }
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
                    write_event(memory_events_path, event_row)
                    write_event(MEMORY_EVENTS_PATH, event_row)
                    run_error_events.append(event)
                    metrics["v2_error_events"] += 1
                seen_error_fingerprints.append(error_fingerprint)

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
                    transfer_max_results=transfer_retrieval_max_results,
                    transfer_score_weight=transfer_retrieval_score_weight,
                )
                for loser in conflict_losers:
                    contradiction_loser_counts[loser] += 1
                if v2_matches:
                    injected_lessons: list[dict[str, Any]] = []
                    retrieval_scores: list[dict[str, Any]] = []
                    lesson_lanes: dict[str, str] = {}
                    hint_lanes: dict[str, str] = {}
                    for match in v2_matches:
                        rule_text = str(match.lesson.rule_text)
                        lane = str(getattr(match, "lane", "strict")).strip().lower() or "strict"
                        lesson_id = str(match.lesson.lesson_id)
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
                            "lesson_ids": [match.lesson.lesson_id for match in v2_matches],
                            "lesson_lanes": lesson_lanes,
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
            if verbose:
                print(f"[step {step:03d}] no tool call; model stopped.", flush=True)
            break
        messages.append({"role": "user", "content": tool_results})

    # --- Evaluation ---
    events = read_events(paths.events_path)

    # Deterministic eval (CONTRACT.json) — works for domains that have contracts
    if has_contract:
        # SQLite-style deterministic eval
        eval_result = evaluate_cli_session(
            task=task_text,
            task_id=task_id,
            events=events,
            db_path=workspace.work_dir / "task.db",
            tasks_root=TASKS_ROOT,
        ).to_dict()
        metrics["eval_passed"] = bool(eval_result.get("passed", False))
        metrics["eval_score"] = float(eval_result.get("score", 0.0) or 0.0)
        metrics["eval_reasons"] = list(eval_result.get("reasons", [])) if isinstance(eval_result.get("reasons"), list) else []
    else:
        eval_result = {"passed": False, "score": 0.0, "reasons": ["no_contract"]}

    # LLM Judge — always run if no contract, or if contract failed
    use_llm_judge = not has_contract or not metrics.get("eval_passed", False)
    if use_llm_judge:
        final_state = adapter.capture_final_state(workspace)
        judge_result: JudgeResult = llm_judge(
            client=client,
            model=effective_judge_model,
            task_text=task_text,
            events=events,
            final_state=final_state,
            domain_name=domain,
        )
        metrics["judge_passed"] = judge_result.passed
        metrics["judge_score"] = judge_result.score
        metrics["judge_reasons"] = judge_result.reasons
        metrics["judge_critique"] = judge_result.raw_response

        # If no CONTRACT exists, use judge as primary eval signal
        if not has_contract:
            metrics["eval_passed"] = judge_result.passed
            metrics["eval_score"] = judge_result.score
            metrics["eval_reasons"] = judge_result.reasons
            eval_result = judge_result.to_dict()

    critic_no_updates = False

    if posttask_learn and skill_manifest_entries:
        # Demo mode keeps Memory V2 lesson generation/promotion active while
        # suppressing legacy skill patching hooks/events for cleaner demos.
        patching_enabled = architecture_mode == "full" and not memory_v2_demo_mode
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
        skill_snapshots, skill_digests = _load_skill_snapshots(entries=skill_manifest_entries, routed_refs=routed_refs)
        domain_keywords = adapter.quality_keywords()
        critic_context = ""
        critic_context_sources: list[str] = []
        if learning_mode == "strict":
            # Strict-only critic retrieval path:
            # adapter exposes domain docs -> retrieval selects relevant chunks ->
            # critic prompt gets only those chunks as contextual grounding.
            docs = adapter.docs_manifest()
            retrieval_query = _build_critic_context_query(
                task_text=task_text,
                eval_result=eval_result,
                events_tail=tail_events,
            )
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
        )
        hard_events = [event for event in run_error_events if event.channel == "hard_failure"]
        fingerprint_counts = Counter(event.fingerprint for event in hard_events)
        recurring_fingerprints = [fingerprint for fingerprint, count in fingerprint_counts.items() if count >= 2]
        prioritized_fingerprints = recurring_fingerprints or [fingerprint for fingerprint, _ in fingerprint_counts.most_common(3)]
        v2_candidates: list[LessonRecord] = []
        for lesson in v2_reflection.filtered_lessons:
            tags = extract_tags(error=lesson.lesson)
            v2_candidates.append(
                LessonRecord.from_candidate(
                    session_id=session_id,
                    task_id=task_id,
                    task=task_text,
                    domain=domain,
                    rule_text=lesson.lesson,
                    trigger_fingerprints=prioritized_fingerprints,
                    tags=tags,
                    status="candidate",
                )
            )
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
        fingerprints_recur_after: set[str] = set()
        for activation in lesson_activation_records:
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
        for lesson_id, bucket in activations_by_lesson.items():
            count = max(1.0, bucket["count"])
            outcomes.append(
                LessonOutcome(
                    lesson_id=lesson_id,
                    error_reduction=bucket["error"] / count,
                    step_efficiency_gain=bucket["eff"] / count,
                    referee_score_gain=referee_gain,
                    major_regression=bool(metrics.get("eval_score", 0.0) < 0.2 and metrics.get("tool_errors", 0) > 0),
                    contradiction_lost=False,
                )
            )
        for lesson_id, count in contradiction_loser_counts.items():
            if count <= 0:
                continue
            outcomes.append(
                LessonOutcome(
                    lesson_id=lesson_id,
                    error_reduction=0.0,
                    step_efficiency_gain=0.0,
                    referee_score_gain=referee_gain,
                    contradiction_lost=True,
                )
            )
        promotion_result_v2 = apply_outcomes(path=LESSONS_V2_PATH, outcomes=outcomes)
        metrics["v2_promoted"] = int(promotion_result_v2.get("promoted", 0))
        metrics["v2_suppressed"] = int(promotion_result_v2.get("suppressed", 0))
        metrics["v2_outcomes_updated"] = int(promotion_result_v2.get("updated", 0))
        metrics["v2_fingerprint_recurrence_after"] = len(fingerprints_recur_after)
        metrics["v2_retrieval_help_ratio"] = round(
            float(helped) / float(max(1, len(lesson_activation_records))),
            4,
        )

        # Simplified architecture stores lessons only and skips post-task skill patches.
        if not patching_enabled:
            metrics["posttask_skill_patching_skipped_by_mode"] = True
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
                parsed_updates, parsed_confidence = parse_reflection_response(reflection_raw)
                if parsed_updates:
                    proposed_updates = parsed_updates
                    confidence = parsed_confidence

            critic_no_updates = len(proposed_updates) == 0
            required_digests = {update.skill_ref: update.skill_digest for update in proposed_updates}
            allowed_refs = {update.skill_ref for update in proposed_updates}

            if posttask_mode == "direct":
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

            write_event(
                paths.events_path,
                {
                    "step": int(metrics["steps"]) + 1,
                    "tool": "posttask_hook",
                    "tool_input": {"mode": posttask_mode, "critic_model": critic_model_for_run},
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
    metrics["elapsed_s"] = round(time.time() - float(metrics["time_start"]), 3)

    write_metrics(paths.metrics_path, metrics)
    return CliRunResult(
        messages=messages,
        metrics=metrics,
        task_text=task_text,
        system_prompt=system_prompt,
        lessons_text=lessons_text,
        tools=tools,
    )
