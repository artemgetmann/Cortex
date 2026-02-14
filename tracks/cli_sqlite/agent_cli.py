from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic

from config import CortexConfig
from tracks.cli_sqlite.domain_adapter import DomainAdapter, DomainWorkspace, ToolResult
from tracks.cli_sqlite.eval_cli import evaluate_cli_session
from tracks.cli_sqlite.judge_llm import JudgeResult, default_judge_model, llm_judge
from tracks.cli_sqlite.learning_cli import generate_lessons, load_relevant_lessons, prune_lessons, store_lessons
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
QUEUE_PATH = LEARNING_ROOT / "pending_skill_patches.json"
PROMOTED_PATH = LEARNING_ROOT / "promoted_skill_patches.json"
ESCALATION_STATE_PATH = LEARNING_ROOT / "critic_escalation_state.json"

DEFAULT_EXECUTOR_MODEL = "claude-haiku-4-5"
DEFAULT_CRITIC_MODEL = "claude-haiku-4-5"
SONNET_MODEL = "claude-sonnet-4-5"
OPUS_MODEL = "claude-opus-4-6"
READ_SKILL_TOOL_NAME = "read_skill"
SHOW_FIXTURE_TOOL_NAME = "show_fixture"


@dataclass
class CliRunResult:
    messages: list[dict[str, Any]]
    metrics: dict[str, Any]


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
        return GridtoolAdapter(cryptic_errors=cryptic_errors, semi_helpful_errors=semi_helpful_errors)
    raise ValueError(f"Unknown domain: {domain!r}. Available: sqlite, gridtool")


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
    bootstrap: bool = False,
    posttask_mode: str = "candidate",
    posttask_learn: bool = True,
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
) -> CliRunResult:
    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key, max_retries=3)
    adapter = _resolve_adapter(domain, cryptic_errors=cryptic_errors, semi_helpful_errors=semi_helpful_errors)

    # Load task text: explicit arg > task.md file > fallback
    task_text = task.strip() if isinstance(task, str) and task.strip() else _load_task_text(TASKS_ROOT, task_id)

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
        skills_text = "(bootstrap mode — no skill docs available. Learn from trial, error messages, and prior lessons.)"
    else:
        routed_entries = route_manifest_entries(task=task_text, entries=skill_manifest_entries, top_k=2)
        routed_refs = [entry.skill_ref for entry in routed_entries]
        required_skill_refs = set(routed_refs[:1]) if require_skill_read else set()
        skills_text = manifest_summaries_text(routed_entries)
    lessons_text, lessons_loaded = load_relevant_lessons(
        path=LESSONS_PATH,
        task_id=task_id,
        task=task_text,
        max_lessons=12,
        max_sessions=8,
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

    # Resolve judge model
    effective_judge_model = model_judge or default_judge_model(model_executor)

    metrics: dict[str, Any] = {
        "session_id": session_id,
        "task_id": task_id,
        "task": task_text,
        "domain": domain,
        "bootstrap": bootstrap,
        "steps": 0,
        "tool_actions": 0,
        "tool_errors": 0,
        "skill_gate_blocks": 0,
        "skill_reads": 0,
        "required_skill_refs": sorted(required_skill_refs),
        "require_skill_read": require_skill_read,
        "lessons_loaded": lessons_loaded,
        "lessons_generated": 0,
        "posttask_patch_attempted": False,
        "posttask_candidates_queued": 0,
        "posttask_patch_applied": 0,
        "auto_promotion_applied": 0,
        "auto_promotion_reason": None,
        "executor_model": model_executor,
        "critic_model": critic_model_for_run,
        "judge_model": effective_judge_model,
        "eval_score": 0.0,
        "eval_reasons": [],
        "eval_passed": False,
        "judge_score": None,
        "judge_passed": None,
        "judge_reasons": [],
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

            if result.is_error():
                metrics["tool_errors"] += 1

            write_event(
                paths.events_path,
                {
                    "step": step,
                    "tool": canonical_name,
                    "tool_input": tool_input,
                    "ok": not result.is_error(),
                    "error": result.error,
                    "output": result.output,
                },
            )

            if verbose:
                print(
                    f"[step {step:03d}] tool={canonical_name} ok={not result.is_error()} error={result.error!r}",
                    flush=True,
                )

            tool_results.append(_tool_result_block(tool_use_id, result))

        if not tool_results:
            if verbose:
                print(f"[step {step:03d}] no tool call; model stopped.", flush=True)
            break
        messages.append({"role": "user", "content": tool_results})

    # --- Evaluation ---
    events = read_events(paths.events_path)

    # Deterministic eval (CONTRACT.json) — works for domains that have contracts
    contract_path = TASKS_ROOT / task_id / "CONTRACT.json"
    if contract_path.exists():
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
    use_llm_judge = not contract_path.exists() or not metrics.get("eval_passed", False)
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

        # If no CONTRACT exists, use judge as primary eval signal
        if not contract_path.exists():
            metrics["eval_passed"] = judge_result.passed
            metrics["eval_score"] = judge_result.score
            metrics["eval_reasons"] = judge_result.reasons
            eval_result = judge_result.to_dict()

    critic_no_updates = False

    if posttask_learn and skill_manifest_entries:
        metrics["posttask_patch_attempted"] = True
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
        lessons = generate_lessons(
            client=client,
            model=critic_model_for_run,
            session_id=session_id,
            task_id=task_id,
            task=task_text,
            eval_result=eval_result,
            events_tail=tail_events,
            skill_refs_used=sorted(read_skill_refs),
            domain_name=domain,
            domain_keywords=domain_keywords,
        )
        metrics["lessons_generated"] = store_lessons(path=LESSONS_PATH, lessons=lessons)
        prune_lessons(LESSONS_PATH, max_per_task=20, domain_keywords=domain_keywords)

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
    return CliRunResult(messages=messages, metrics=metrics)
