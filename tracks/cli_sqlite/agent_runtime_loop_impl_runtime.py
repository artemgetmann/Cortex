from __future__ import annotations

from typing import Any, Mapping

from tracks.cli_sqlite import agent_cli as _agent_cli
from tracks.cli_sqlite.agent_runtime_arg_builders import (
    build_finalize_args,
    build_metrics_init_args,
    build_post_execution_args,
    build_prompt_context_args,
)
from tracks.cli_sqlite.agent_runtime_contract_gap import (
    ContractGapRetryState,
    maybe_inject_contract_gap_retry,
    run_contract_postretry_validator,
)
from tracks.cli_sqlite.agent_runtime_finalize import finalize_runtime_run
from tracks.cli_sqlite.agent_runtime_metrics import init_runtime_metrics
from tracks.cli_sqlite.agent_runtime_post_execution import run_post_execution_phases

_RUNTIME_LOOP_IMPL_LOCAL_SYMBOLS = {
    "_agent_cli",
    "_RUNTIME_LOOP_IMPL_LOCAL_SYMBOLS",
    "_sync_runtime_symbols",
    "_hydrate_runtime_symbols",
    "_run_cli_agent_impl_extracted",
}


def _sync_runtime_symbols() -> None:
    """Mirror agent_cli globals so runtime behavior matches legacy module."""
    for _name, _value in vars(_agent_cli).items():
        if _name.startswith("__"):
            continue
        if _name in _RUNTIME_LOOP_IMPL_LOCAL_SYMBOLS:
            continue
        globals()[_name] = _value


def _hydrate_runtime_symbols(runtime_symbols: Mapping[str, Any] | None) -> None:
    if runtime_symbols is None:
        return
    for _name, _value in runtime_symbols.items():
        if _name.startswith("__"):
            continue
        if _name in _RUNTIME_LOOP_IMPL_LOCAL_SYMBOLS:
            continue
        globals()[_name] = _value


_sync_runtime_symbols()

def _run_cli_agent_impl_extracted(
    *,
    runtime_symbols: Mapping[str, Any] | None = None,
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
    _sync_runtime_symbols()
    _hydrate_runtime_symbols(runtime_symbols)
    learning_mode = _normalize_learning_mode(learning_mode)
    architecture_mode = _normalize_architecture_mode(architecture_mode)
    # Local retrieval provider is intentionally lightweight and deterministic.
    # Strict mode uses it for critic context; legacy ignores it.
    knowledge_provider = LocalDocsKnowledgeProvider()
    transfer_retrieval_max_results = max(0, int(transfer_retrieval_max_results))
    transfer_retrieval_score_weight = max(0.0, float(transfer_retrieval_score_weight))
    doc_mode = normalize_doc_mode(doc_mode)
    doc_retrieval = normalize_doc_retrieval_mode(doc_retrieval)
    executor_prompt_mode = _normalize_executor_prompt_mode(executor_prompt_mode)
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
    # In strict structured mode, legacy free-text hints are intentionally disabled
    # so learning signal comes from executable V2 lessons only.
    legacy_lessons_enabled = (not benchmark_promoted_only) and (not bool(structured_lessons_required))
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
    elif llm_backend in {"openai", "openai_agents_sdk"}:
        if not openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when llm_backend is an OpenAI transport.")
        client = (
            _OpenAICompatClient(api_key=openai_api_key)
            if llm_backend == "openai"
            else _OpenAIAgentsSDKCompatClient(api_key=openai_api_key)
        )
    else:
        client = ClaudePrintClient()
    adapter = _resolve_adapter_with_mode(
        domain,
        cryptic_errors=cryptic_errors,
        semi_helpful_errors=semi_helpful_errors,
        mixed_errors=mixed_errors,
    )

    paths = ensure_session(session_id, sessions_root=SESSIONS_ROOT, reset_existing=True)

    # Prepare domain workspace
    task_dir = TASKS_ROOT / task_id
    if not task_dir.exists():
        raise FileNotFoundError(f"Unknown task id: {task_id!r} (missing {task_dir})")
    workspace: DomainWorkspace = adapter.prepare_workspace(task_dir, paths.session_dir)

    # Build full manifest always (needed for posttask learning even in bootstrap)
    skill_manifest_entries = build_skill_manifest(skills_root=SKILLS_ROOT, manifest_path=MANIFEST_PATH)
    self_edit_manifest_entries = build_self_edit_manifest_entries(track_root=TRACK_ROOT) if bool(self_edit_mode) else []
    self_edit_mode_active = bool(self_edit_mode) and bool(self_edit_manifest_entries)
    self_edit_refs = {entry.skill_ref for entry in self_edit_manifest_entries}

    runtime_contract: dict[str, Any] | None = None
    try:
        # Runtime path includes workspace override so session-seeded contracts
        # (for transfer-hard variants) can drive prompt checklist guidance.
        runtime_contract, _ = load_contract(TASKS_ROOT, task_id, work_dir=workspace.work_dir)
    except Exception:
        runtime_contract = None
    prompt_context = build_runtime_prompt_context(
        **build_prompt_context_args(local_ctx=locals(), deps=globals())
    )
    docs_bundle = prompt_context.docs_bundle
    if docs_bundle is None:
        raise RuntimeError("Runtime docs bundle missing while preload_docs_bundle=True.")

    task_text = prompt_context.task_text
    routed_entries = prompt_context.routed_entries
    routed_refs = prompt_context.routed_refs
    required_skill_refs = prompt_context.required_skill_refs
    lessons_text = prompt_context.lessons_text
    lessons_loaded = prompt_context.lessons_loaded
    prerun_v2_matches = prompt_context.prerun_v2_matches
    prerun_v2_ids = prompt_context.prerun_v2_ids
    loaded_lesson_objects = prompt_context.loaded_lesson_objects
    docs_executor_block = prompt_context.docs_executor_block
    docs_judge_block = prompt_context.docs_judge_block
    docs_prompt_available = prompt_context.docs_prompt_available
    docs_selected_source_ids = prompt_context.docs_selected_source_ids
    docs_read_error_entries = prompt_context.docs_read_error_entries
    system_prompt = prompt_context.system_prompt
    tools = prompt_context.tools

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

    alias_map = adapter.build_alias_map(opaque=opaque_tools)

    messages: list[dict[str, Any]] = [{"role": "user", "content": [{"type": "text", "text": task_text}]}]
    # Build a name->schema map for tool-agnostic input validation. This keeps
    # validation structural (required keys, primitive types) instead of semantic.
    tool_schema_map = build_tool_schema_map(tools)

    escalation_state = _load_escalation_state(base_model=model_critic)
    critic_model_for_run, escalation_state = _resolve_critic_model_for_run(
        base_model=model_critic,
        auto_escalate=auto_escalate_critic,
        state=escalation_state,
    )
    if llm_backend in {"openai", "openai_agents_sdk"}:
        normalized_critic_model = str(critic_model_for_run or "").strip().lower()
        # OpenAI-backed runs must not "escalate" into Anthropic model names.
        # That does not make the critic stronger; it just creates a broken call
        # path and silently kills lesson generation. Keep the critic on the
        # caller-selected OpenAI family unless the caller explicitly passed a
        # compatible OpenAI model.
        if not normalized_critic_model.startswith(("gpt-", "o1", "o3", "o4")):
            critic_model_for_run = model_critic
            escalation_state["tier"] = _tier_from_model(model_critic)
            escalation_state["override_runs_remaining"] = 0
            escalation_state["last_trigger"] = "backend_family_lock"

    contract_path = TASKS_ROOT / task_id / "CONTRACT.json"
    has_contract = contract_path.exists()

    # Simplified architecture removes the separate judge model and reuses executor.
    if architecture_mode == "simplified":
        effective_judge_model = model_executor
    elif llm_backend in {"openai", "openai_agents_sdk"}:
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

    metrics: dict[str, Any] = init_runtime_metrics(
        **build_metrics_init_args(local_ctx=locals())
    )

    executor_tool_name = adapter.executor_tool_name
    read_skill_refs: set[str] = set()
    run_error_events: list[ErrorEvent] = []
    seen_error_fingerprints: list[str] = []
    reflection_pending: str | None = None
    reflection_threshold_triggered = False
    reflection_fingerprints: set[str] = set()
    contract_gap_state = ContractGapRetryState()
    no_tool_recovery_prompts_used = 0
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

    def _emit_step_lifecycle(*, current_step: int, trigger: str) -> None:
        """Emit compact lifecycle breadcrumbs for transport UIs.

        The Telegram bridge polls run lifecycle events, so this callback is the
        cheapest place to expose actionable live state without coupling UI code
        to executor internals.
        """
        if on_lifecycle_event is None:
            return
        trigger_text = str(trigger or "").strip()
        if not trigger_text:
            return
        try:
            on_lifecycle_event("step", {"step": int(current_step), "trigger": trigger_text})
        except Exception:
            # Lifecycle telemetry is best-effort and must never alter run behavior.
            return

    def _tool_trigger_suffix(tool_name: str, tool_input: dict[str, Any]) -> str:
        # Keep progress payload compact; Telegram cards should show intent, not
        # full command/sql blobs that can exceed message limits.
        if tool_name == "run_bash":
            command = " ".join(str(tool_input.get("command", "")).split())
            if command:
                return f" cmd={_clip_text(command, max_chars=96)}"
        if tool_name == "run_sqlite":
            sql_text = " ".join(str(tool_input.get("sql", "")).split())
            if sql_text:
                return f" sql={_clip_text(sql_text, max_chars=96)}"
        return ""

    if prerun_v2_ids:
        _emit_step_lifecycle(
            current_step=0,
            trigger=f"lessons:prerun:{len(prerun_v2_ids)}",
        )

    contradiction_loser_counts: dict[str, int] = defaultdict(int)
    repeated_error_signatures: list[str] = []
    promoted_lesson_ids: list[str] = []
    suppressed_lesson_ids: list[str] = []
    v2_candidate_lessons: list[dict[str, Any]] = []
    executor_input_bundles: list[dict[str, Any]] = []
    judge_input_bundle: dict[str, Any] | None = None
    judge_payload_bundle: dict[str, Any] | None = None

    # Contract-gap retry logic was extracted into a dedicated module to keep
    # this runtime loop focused on orchestration.
    def _maybe_inject_contract_gap_retry(*, current_step: int, trigger: str) -> bool:
        return maybe_inject_contract_gap_retry(
            state=contract_gap_state,
            current_step=current_step,
            trigger=trigger,
            has_contract=has_contract,
            contract_gap_retry=bool(contract_gap_retry),
            contract_gap_retry_steps=int(contract_gap_retry_steps),
            contract_gap_deterministic_recipes=bool(contract_gap_deterministic_recipes),
            task_text=task_text,
            task_id=task_id,
            domain=domain,
            benchmark_placebo=bool(benchmark_placebo),
            structured_lessons_required=bool(structured_lessons_required),
            enable_transfer_retrieval=enable_transfer_retrieval,
            transfer_retrieval_policy=transfer_retrieval_policy,
            transfer_retrieval_max_results=transfer_retrieval_max_results,
            transfer_retrieval_score_weight=transfer_retrieval_score_weight,
            runtime_candidate_policy_effective=runtime_candidate_policy_effective,
            lessons_v2_path=LESSONS_V2_PATH,
            tasks_root=TASKS_ROOT,
            adapter=adapter,
            workspace=workspace,
            paths=paths,
            metrics=metrics,
            messages=messages,
            lesson_activation_records=lesson_activation_records,
            on_lifecycle_event=on_lifecycle_event,
            verbose=verbose,
            canonicalize_hotfix_transfer_eval_events_fn=_canonicalize_hotfix_transfer_eval_events,
            read_events_fn=read_events,
            evaluate_cli_session_fn=evaluate_cli_session,
            unresolved_contract_gaps_fn=unresolved_contract_gaps,
            run_shell_hotfix_transfer_closure_check_fn=_run_shell_hotfix_transfer_closure_check,
            write_event_fn=write_event,
            clip_text_fn=lambda text: _clip_text(text, max_chars=900),
            adaptive_gap_lesson_cap_fn=_adaptive_gap_lesson_cap,
            retrieve_on_error_fn=retrieve_on_error,
            select_gap_targeted_matches_fn=_select_gap_targeted_matches,
            placebo_hint_for_lesson_fn=_placebo_hint_for_lesson,
            deterministic_gap_fix_recipes_fn=_deterministic_gap_fix_recipes,
            format_contract_gap_retry_prompt_fn=_format_contract_gap_retry_prompt,
        )

    def _run_contract_postretry_validator(*, current_step: int, trigger: str) -> None:
        run_contract_postretry_validator(
            state=contract_gap_state,
            current_step=current_step,
            trigger=trigger,
            adapter=adapter,
            workspace=workspace,
            paths=paths,
            metrics=metrics,
            write_event_fn=write_event,
        )

    step = 1
    validation_retries_this_step = 0
    validation_retry_capped_this_step = False
    sdk_execution_state = _OpenAIAgentsSDKExecutionState() if llm_backend == "openai_agents_sdk" else None
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
        # Generic task-mode escalation: after a no-tool recovery prompt has
        # already been injected, stop relying on the model to volunteer tool
        # use. Require one tool call so the loop keeps interacting with the
        # environment instead of burning turns on pure reasoning.
        tool_choice_override = None
        if (
            llm_backend == "openai"
            and no_tool_recovery_prompts_used > 0
            and step < max_steps
            and bool(tools)
        ):
            tool_choice_override = "required"
            executor_input_bundle["tool_choice_override"] = "required"
        assistant_blocks, usage = request_executor_turn(
            llm_backend=llm_backend,
            client=client,
            openai_api_key=openai_api_key,
            model=model_executor,
            system_prompt=system_prompt,
            tools=tools,
            messages=messages,
            runtime_temperature=runtime_temperature,
            tool_choice_override=tool_choice_override,
            prompt_logger=lambda prompt_text: executor_input_bundle.__setitem__("claude_print_prompt", prompt_text),
            claude_print_fallback_model=DEFAULT_EXECUTOR_MODEL,
            claude_print_request_fn=_create_executor_response_via_claude_print,
            sdk_execution_state=sdk_execution_state,
            sdk_execution_context=True,
        )
        metrics["usage"].append(usage)
        # Keep compact per-turn response-shape diagnostics when transports
        # provide them (for example OpenAI Agents SDK output item summaries).
        if isinstance(usage, dict):
            response_diag: dict[str, Any] = {}
            for key in (
                "output_tokens",
                "output_item_count",
                "output_item_type_counts",
                "function_call_count",
                "tool_parse_errors",
                "text_block_count",
                "reasoning_only_turn",
                "retry_attempted",
                "retry_succeeded",
                "continuity_mode",
                "sdk_tool_choice_effective",
                "sdk_callback_invocation_count",
                "sdk_callback_bridge_used",
                "sdk_no_tool_reason",
                "sdk_no_tool_reason_effective",
                "sdk_local_no_tool_retry_attempted",
                "sdk_local_no_tool_retry_succeeded",
                "sdk_local_no_tool_retry_error",
                "sdk_local_no_tool_retry_forced_full_history",
            ):
                if key in usage:
                    response_diag[key] = usage.get(key)
            if response_diag:
                metrics["last_model_response_diag"] = response_diag
                if llm_backend == "openai_agents_sdk":
                    output_tokens = int(response_diag.get("output_tokens", 0) or 0)
                    reasoning_only_turn = bool(response_diag.get("reasoning_only_turn", False))
                    retry_attempted = bool(
                        response_diag.get(
                            "retry_attempted",
                            response_diag.get("sdk_local_no_tool_retry_attempted", False),
                        )
                    )
                    retry_succeeded = bool(
                        response_diag.get(
                            "retry_succeeded",
                            response_diag.get("sdk_local_no_tool_retry_succeeded", False),
                        )
                    )
                    if reasoning_only_turn:
                        metrics["sdk_reasoning_only_turns"] = int(metrics.get("sdk_reasoning_only_turns", 0) or 0) + 1
                        metrics["sdk_reasoning_only_output_tokens"] = int(
                            metrics.get("sdk_reasoning_only_output_tokens", 0) or 0
                        ) + output_tokens
                    if retry_attempted:
                        metrics["sdk_no_tool_retry_attempted"] = int(
                            metrics.get("sdk_no_tool_retry_attempted", 0) or 0
                        ) + 1
                    if retry_succeeded:
                        metrics["sdk_no_tool_retry_succeeded"] = int(
                            metrics.get("sdk_no_tool_retry_succeeded", 0) or 0
                        ) + 1
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
                    if contract_gap_state.contract_retry_post_validation_pending:
                        contract_gap_state.contract_retry_repair_observed = True
                        repair_steps = list(metrics.get("contract_retry_repair_steps", []) or [])
                        repair_steps.append(int(step))
                        metrics["contract_retry_repair_steps"] = sorted(set(repair_steps))
                        _run_contract_postretry_validator(
                            current_step=step,
                            trigger="post_retry_after_repair",
                        )
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
                on_error_cap = _adaptive_gap_lesson_cap(
                    unresolved_gaps=contract_gap_state.latest_unresolved_gaps,
                    min_cap=1,
                    max_cap=3,
                )
                v2_matches, conflict_losers = retrieve_on_error(
                    path=LESSONS_V2_PATH,
                    error_text=error_text,
                    fingerprint=error_fingerprint,
                    domain=domain,
                    task_id=task_id,
                    query_tags=error_tags,
                    max_results=8,
                    include_domainless=False,
                    enable_transfer=enable_transfer_retrieval,
                    transfer_policy=transfer_retrieval_policy,
                    transfer_max_results=transfer_retrieval_max_results,
                    transfer_score_weight=transfer_retrieval_score_weight,
                    unresolved_gaps=contract_gap_state.latest_unresolved_gaps,
                    candidate_policy=runtime_candidate_policy_effective,
                    strict_gap_signature_match=bool(structured_lessons_required),
                    enforce_executable_schema=bool(structured_lessons_required),
                    rejection_counters=metrics["v2_schema_rejection_counts"],
                )
                v2_matches = _select_gap_targeted_matches(
                    matches=v2_matches,
                    unresolved_gaps=contract_gap_state.latest_unresolved_gaps,
                    max_lessons=on_error_cap,
                    min_score=0.25,
                    current_error_text=error_text,
                )
                metrics["v2_on_error_adaptive_lesson_cap"] = int(on_error_cap)
                metrics["v2_on_error_lessons_selected"] = int(len(v2_matches))
                for loser in conflict_losers:
                    contradiction_loser_counts[loser] += 1
                if v2_matches:
                    injected_lessons: list[dict[str, Any]] = []
                    retrieval_scores: list[dict[str, Any]] = []
                    lesson_lanes: dict[str, str] = {}
                    hint_lanes: dict[str, str] = {}
                    for match in v2_matches:
                        lesson_id = str(match.lesson.lesson_id)
                        # Soft firewall: keep retrieval active, but avoid
                        # injecting low-trust raw command blobs directly into the
                        # next model turn. Risky lessons are rewritten into safe
                        # summary hints instead of being deleted.
                        rule_text, trust_band, hint_mode = _render_runtime_lesson_hint(
                            lesson=match.lesson,
                            use_placebo=bool(benchmark_placebo),
                            task_id=task_id,
                            domain=domain,
                        )
                        lane = str(getattr(match, "lane", "strict")).strip().lower() or "strict"
                        v2_hints.append(rule_text)
                        injected_lessons.append(
                            {
                                "lesson_id": lesson_id,
                                "rule_text": rule_text,
                                "lane": lane,
                                "trust_band": trust_band,
                                "hint_mode": hint_mode,
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
                        if trust_band == "risky":
                            metrics["v2_lesson_risky_count"] = int(metrics.get("v2_lesson_risky_count", 0) or 0) + 1
                        if hint_mode != "direct_action":
                            metrics["v2_lesson_firewall_rewrites"] = int(
                                metrics.get("v2_lesson_firewall_rewrites", 0) or 0
                            ) + 1
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
                    lesson_preview = ",".join(str(match.lesson.lesson_id) for match in v2_matches[:3])
                    _emit_step_lifecycle(
                        current_step=step,
                        trigger=(
                            f"lessons:on_error:{len(v2_hints)}"
                            + (f" ids={_clip_text(lesson_preview, max_chars=72)}" if lesson_preview else "")
                        ),
                    )

                # Legacy fallback keeps older runs usable while v2 memory warms up.
                legacy_hints: list[str] = []
                if not v2_hints and loaded_lesson_objects and not bool(structured_lessons_required):
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
                        _emit_step_lifecycle(
                            current_step=step,
                            trigger=f"lessons:legacy:{len(legacy_hints)}",
                        )

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
            _emit_step_lifecycle(
                current_step=step,
                trigger=(
                    f"tool:{canonical_name}:{'ok' if not result.is_error() else 'error'}"
                    + _tool_trigger_suffix(canonical_name, tool_input)
                ),
            )

            tool_results.append(_tool_result_block(tool_use_id, result))

        if not tool_results:
            # Centralized no-tool accounting keeps backend behavior stable and
            # unit-testable when transport logic changes (OpenAI vs SDK).
            write_event(
                paths.events_path,
                record_no_tool_call_event(
                    metrics=metrics,
                    llm_backend=llm_backend,
                    last_model_response_diag=metrics.get("last_model_response_diag"),
                    step=step,
                ),
            )
            if llm_backend == "openai_agents_sdk" and sdk_execution_state is not None:
                # Reset continuity before any early-continue branch.
                # Without this ordering, the contract-gap retry branch can skip
                # the reset and leave the SDK stuck in delta-mode no-tool loops.
                sdk_execution_state.previous_response_id = None
                sdk_execution_state.last_source_message_count = 0
                sdk_execution_state.continuation_input_items = []
                metrics["sdk_no_tool_continuity_resets"] = int(metrics.get("sdk_no_tool_continuity_resets", 0) or 0) + 1
                reset_steps = list(metrics.get("sdk_no_tool_continuity_reset_steps", []) or [])
                reset_steps.append(int(step))
                metrics["sdk_no_tool_continuity_reset_steps"] = reset_steps
            if contract_gap_state.contract_retry_post_validation_pending:
                _run_contract_postretry_validator(
                    current_step=step,
                    trigger="no_tool_call",
                )
            if _maybe_inject_contract_gap_retry(current_step=step, trigger="no_tool_call"):
                continue
            if should_inject_no_tool_recovery_prompt(
                step=step,
                max_steps=max_steps,
                used_prompts=no_tool_recovery_prompts_used,
                max_prompts=MAX_NO_TOOL_RECOVERY_PROMPTS,
            ):
                # Deterministic recovery path for text-only/empty model turns.
                # This is domain-agnostic: require exactly one executable tool
                # call so the loop can continue collecting real feedback.
                no_tool_recovery_prompts_used += 1
                metrics["no_tool_recovery_prompts"] = int(metrics.get("no_tool_recovery_prompts", 0) or 0) + 1
                recovery_text = build_no_tool_recovery_prompt(executor_tool_name=executor_tool_name)
                messages.append({"role": "user", "content": [{"type": "text", "text": recovery_text}]})
                if verbose:
                    print(
                        (
                            f"[step {step:03d}] no tool call; forcing recovery prompt "
                            f"{no_tool_recovery_prompts_used}/{MAX_NO_TOOL_RECOVERY_PROMPTS}."
                        ),
                        flush=True,
                    )
                _emit_step_lifecycle(
                    current_step=step,
                    trigger="recovery:no_tool_prompt",
                )
                step += 1
                validation_retries_this_step = 0
                validation_retry_capped_this_step = False
                continue
            if verbose:
                print(f"[step {step:03d}] no tool call; model stopped.", flush=True)
            _emit_step_lifecycle(
                current_step=step,
                trigger="stop:no_tool_call",
            )
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
        if step >= max_steps:
            if contract_gap_state.contract_retry_post_validation_pending:
                _run_contract_postretry_validator(
                    current_step=step,
                    trigger="step_cap",
                )
            if _maybe_inject_contract_gap_retry(current_step=step, trigger="step_cap"):
                # Retry executes at the same logical step so the deterministic gap
                # close does not consume additional user-visible step budget.
                validation_retries_this_step = 0
                validation_retry_capped_this_step = False
                continue
        step += 1
        validation_retries_this_step = 0
        validation_retry_capped_this_step = False

    if contract_gap_state.contract_retry_post_validation_pending:
        _run_contract_postretry_validator(
            current_step=int(metrics.get("steps", step) or step),
            trigger="loop_exit",
        )

    # --- Evaluation + verifier + posttask ---
    if contract_gap_state.contract_gap_prestop_artifacts:
        metrics["contract_gap_prestop_artifacts"] = list(contract_gap_state.contract_gap_prestop_artifacts)
    post_execution = run_post_execution_phases(
        **build_post_execution_args(local_ctx=locals(), deps=globals())
    )
    events = post_execution.events
    eval_result = post_execution.eval_result
    probe_result = post_execution.probe_result
    final_unresolved_gaps = post_execution.final_unresolved_gaps
    judge_input_bundle = post_execution.judge_input_bundle
    judge_payload_bundle = post_execution.judge_payload_bundle
    contract_gap_state.latest_unresolved_gaps = final_unresolved_gaps
    repeated_error_signatures = list(post_execution.repeated_error_signatures)
    loop_watchdog_decision = post_execution.loop_watchdog_decision
    loop_watchdog_safe_mode_active = bool(post_execution.loop_watchdog_safe_mode_active)
    loop_watchdog_failure_signals = list(post_execution.loop_watchdog_failure_signals)
    loop_watchdog_stop_flag = bool(post_execution.loop_watchdog_stop_flag)
    effective_self_edit_mode_active = bool(post_execution.effective_self_edit_mode_active)
    watchdog_disable_posttask_effective = bool(post_execution.watchdog_disable_posttask_effective)
    critic_no_updates = bool(post_execution.critic_no_updates)
    v2_candidate_lessons = list(post_execution.v2_candidate_lessons)
    promoted_lesson_ids = list(post_execution.promoted_lesson_ids)
    suppressed_lesson_ids = list(post_execution.suppressed_lesson_ids)

    return finalize_runtime_run(
        **build_finalize_args(local_ctx=locals(), deps=globals())
    )
