from __future__ import annotations

from typing import Any, Mapping

from tracks.cli_sqlite import agent_cli as _agent_cli

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
        task_id=task_id,
        task=task,
        domain=domain,
        adapter=adapter,
        track_root=TRACK_ROOT,
        tasks_root=TASKS_ROOT,
        skills_root=SKILLS_ROOT,
        manifest_path=MANIFEST_PATH,
        lessons_path=LESSONS_PATH,
        lessons_v2_path=LESSONS_V2_PATH,
        fixture_refs=sorted(workspace.fixture_paths.keys()),
        bootstrap=bootstrap,
        require_skill_read=require_skill_read,
        opaque_tools=opaque_tools,
        legacy_lessons_enabled=legacy_lessons_enabled,
        benchmark_placebo=benchmark_placebo,
        runtime_candidate_policy_effective=runtime_candidate_policy_effective,
        runtime_contract=runtime_contract,
        llm_client=client,
        documentation=documentation,
        doc_mode=doc_mode,
        doc_retrieval=doc_retrieval,
        doc_budget_tokens=doc_budget_tokens,
        doc_retriever_model=doc_retriever_model,
        preload_docs_bundle=True,
        executor_docs=executor_docs,
        judge_docs=judge_docs,
        docs_prompt_max_chars=9000,
        executor_prompt_mode=executor_prompt_mode,
        load_task_text_fn=_load_task_text,
        prioritize_domain_routed_entries_fn=_prioritize_domain_routed_entries,
        required_skill_refs_for_domain_fn=_required_skill_refs_for_domain,
        select_high_signal_prerun_matches_fn=_select_high_signal_prerun_matches,
        format_v2_lesson_block_fn=_format_v2_lesson_block,
        format_legacy_placebo_lesson_block_fn=_format_legacy_placebo_lesson_block,
        build_system_prompt_fn=_build_system_prompt,
        build_contract_execution_guidance_fn=_build_contract_execution_guidance_from_contract,
        build_sqlite_validator_guidance_fn=_build_sqlite_validator_guidance_from_contract,
        build_skill_manifest_fn=build_skill_manifest,
        route_manifest_entries_fn=route_manifest_entries,
        manifest_summaries_text_fn=manifest_summaries_text,
        load_relevant_lessons_fn=load_relevant_lessons,
        migrate_legacy_lessons_fn=migrate_legacy_lessons,
        retrieve_pre_run_fn=retrieve_pre_run,
        load_lesson_objects_fn=load_lesson_objects,
        build_documentation_bundle_fn=build_documentation_bundle,
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
        "no_tool_call_steps": 0,
        "no_tool_call_steps_by_backend": {},
        "no_tool_recovery_prompts": 0,
        "sdk_no_tool_continuity_resets": 0,
        "sdk_no_tool_continuity_reset_steps": [],
        "tool_validation_errors": 0,
        "tool_validation_retry_attempts": 0,
        "tool_validation_retry_capped_events": 0,
        # Unified top-line error metric used for learning curves.
        # This intentionally counts execution/tool errors + validation errors
        # + structured memory error events so "error trend" is visible across
        # attempts without requiring downstream code to recompute it.
        "error_count": 0,
        "skill_gate_blocks": 0,
        "skill_reads": 0,
        "required_skill_refs": sorted(required_skill_refs),
        "require_skill_read": require_skill_read,
        "lessons_loaded": lessons_loaded,
        "v2_lessons_loaded": len(prerun_v2_ids),
        "v2_prerun_lesson_ids": prerun_v2_ids,
        "v2_prerun_lesson_activations": len(prerun_v2_ids),
        "v2_prerun_placebo_applied": bool(benchmark_placebo and prerun_v2_ids),
        # Pre-run prompt injections are real lesson activations and should be
        # counted in the same top-line metric users watch during live runs.
        "lesson_activations": len(prerun_v2_ids),
        "v2_lesson_activations": len(prerun_v2_ids),
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
        "contract_gap_deterministic_recipes_enabled": bool(contract_gap_deterministic_recipes),
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
        "contract_gap_deterministic_hint_count": 0,
        "contract_retry_repair_observed": False,
        "contract_retry_repair_steps": [],
        "contract_validator_postretry_runs": 0,
        "contract_validator_postretry_last_status": "not_run",
        "contract_validator_postretry_last_trigger": "",
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
        "v2_structured_fallback_lessons": 0,
        "v2_schema_rejection_counts": {
            "missing_trigger_gap_signature": 0,
            "unbound_trigger_gap_signature": 0,
            "missing_action_template": 0,
            "invalid_action_template_placeholder": 0,
            "invalid_action_template_shape": 0,
            "invalid_action_template_tool": 0,
            "missing_expected_evidence": 0,
            "expected_evidence_unanchored": 0,
            "missing_structured_gap_fields": 0,
        },
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
        "critic_generation_error": "",
        "critic_generation_parsed_items": 0,
        "critic_generation_raw_chars": 0,
        "v2_generation_error": "",
        "v2_generation_parsed_items": 0,
        "v2_generation_raw_chars": 0,
        "loop_watchdog_enabled": True,
        "loop_watchdog_state_path": str(loop_watchdog_state_path),
        "loop_watchdog_safe_mode_initial": bool(loop_watchdog_state.safe_mode_active),
        "loop_watchdog_safe_mode_active": bool(loop_watchdog_safe_mode_active),
        "loop_watchdog_safe_mode_triggered": False,
        "loop_watchdog_failure_signals": [],
        "loop_watchdog_disable_self_edit": False,
        "loop_watchdog_disable_posttask_patching": False,
        "loop_watchdog_disable_posttask_patching_effective": False,
        "watchdog_allow_posttask_in_safe_mode": bool(watchdog_allow_posttask_in_safe_mode),
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
    contract_retry_validator_sql = ""
    contract_retry_validator_query_ids: list[str] = []
    contract_retry_post_validation_pending = False
    contract_retry_repair_observed = False
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
        nonlocal contract_retry_validator_sql, contract_retry_validator_query_ids
        nonlocal contract_retry_post_validation_pending, contract_retry_repair_observed
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
        # Prioritize query-mismatch gaps before pattern-only gaps so retry
        # prompts and deterministic recipes focus on state-correction first.
        gap_priority = {
            "required_query_mismatch": 0,
            "missing_required_pattern": 1,
            "too_many_errors": 2,
            "matched_forbidden_pattern": 3,
        }
        unresolved_gaps = sorted(
            unresolved_gaps,
            key=lambda row: (
                int(gap_priority.get(str(row.get("reason_code", "")).strip(), 9)),
                str(row.get("gap_type", "")).strip(),
                str(row.get("detail", "")).strip(),
            ),
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
        contract_retry_validator_sql = ""
        contract_retry_validator_query_ids = []
        contract_retry_post_validation_pending = False
        contract_retry_repair_observed = False
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
                    contract_retry_validator_sql = validator_sql
                    contract_retry_validator_query_ids = list(query_ids)
                    contract_retry_post_validation_pending = True
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

        gap_cap = _adaptive_gap_lesson_cap(unresolved_gaps=unresolved_gaps, min_cap=1, max_cap=3)
        gap_matches, _ = retrieve_on_error(
            path=LESSONS_V2_PATH,
            error_text=gap_query,
            fingerprint="",
            domain=domain,
            task_id=task_id,
            query_tags=gap_tags,
            max_results=8,
            include_domainless=False,
            enable_transfer=enable_transfer_retrieval,
            transfer_policy=transfer_retrieval_policy,
            transfer_max_results=transfer_retrieval_max_results,
            transfer_score_weight=transfer_retrieval_score_weight,
            unresolved_gaps=unresolved_gaps,
            candidate_policy=runtime_candidate_policy_effective,
            strict_gap_signature_match=bool(structured_lessons_required),
            enforce_executable_schema=bool(structured_lessons_required),
            rejection_counters=metrics["v2_schema_rejection_counts"],
        )
        gap_matches = _select_gap_targeted_matches(
            matches=gap_matches,
            unresolved_gaps=unresolved_gaps,
            max_lessons=gap_cap,
            min_score=0.30,
        )
        metrics["contract_gap_adaptive_lesson_cap"] = int(gap_cap)
        metrics["contract_gap_lessons_selected"] = int(len(gap_matches))
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
        deterministic_gap_hints = (
            _deterministic_gap_fix_recipes(
                adapter=adapter,
                domain=domain,
                task_id=task_id,
                unresolved_gaps=unresolved_gaps,
                max_items=3,
            )
            if bool(contract_gap_deterministic_recipes)
            else []
        )
        metrics["contract_gap_deterministic_hint_count"] = len(deterministic_gap_hints)
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
            deterministic_recipes=deterministic_gap_hints,
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

    def _run_contract_postretry_validator(*, current_step: int, trigger: str) -> None:
        nonlocal contract_retry_post_validation_pending
        if not contract_retry_post_validation_pending:
            return
        validator_sql = str(contract_retry_validator_sql or "").strip()
        if not validator_sql:
            contract_retry_post_validation_pending = False
            return
        validator_result = adapter.execute(
            adapter.executor_tool_name,
            {"sql": validator_sql},
            workspace,
        )
        metrics["contract_validator_postretry_runs"] = int(metrics.get("contract_validator_postretry_runs", 0) or 0) + 1
        metrics["contract_validator_postretry_last_status"] = "ok" if not validator_result.is_error() else "error"
        metrics["contract_validator_postretry_last_trigger"] = str(trigger)
        metrics["contract_retry_repair_observed"] = bool(contract_retry_repair_observed)
        write_event(
            paths.events_path,
            {
                "step": current_step,
                "tool": "contract_validator_postretry",
                "tool_input": {
                    "query_ids": list(contract_retry_validator_query_ids),
                    "sql": validator_sql,
                    "trigger": trigger,
                    "repair_observed": bool(contract_retry_repair_observed),
                },
                "ok": not validator_result.is_error(),
                "error": validator_result.error,
                "output": validator_result.output,
            },
        )
        contract_retry_post_validation_pending = False

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
        assistant_blocks, usage = request_executor_turn(
            llm_backend=llm_backend,
            client=client,
            openai_api_key=openai_api_key,
            model=model_executor,
            system_prompt=system_prompt,
            tools=tools,
            messages=messages,
            runtime_temperature=runtime_temperature,
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
                "output_item_count",
                "output_item_type_counts",
                "function_call_count",
                "text_block_count",
                "continuity_mode",
                "sdk_tool_choice_effective",
                "sdk_callback_invocation_count",
                "sdk_callback_bridge_used",
                "sdk_local_no_tool_retry_attempted",
                "sdk_local_no_tool_retry_succeeded",
                "sdk_local_no_tool_retry_error",
                "sdk_local_no_tool_retry_forced_full_history",
            ):
                if key in usage:
                    response_diag[key] = usage.get(key)
            if response_diag:
                metrics["last_model_response_diag"] = response_diag
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
                    if contract_retry_post_validation_pending:
                        contract_retry_repair_observed = True
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
                    unresolved_gaps=latest_unresolved_gaps,
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
                    unresolved_gaps=latest_unresolved_gaps,
                    candidate_policy=runtime_candidate_policy_effective,
                    strict_gap_signature_match=bool(structured_lessons_required),
                    enforce_executable_schema=bool(structured_lessons_required),
                    rejection_counters=metrics["v2_schema_rejection_counts"],
                )
                v2_matches = _select_gap_targeted_matches(
                    matches=v2_matches,
                    unresolved_gaps=latest_unresolved_gaps,
                    max_lessons=on_error_cap,
                    min_score=0.25,
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
            if contract_retry_post_validation_pending:
                _run_contract_postretry_validator(
                    current_step=step,
                    trigger="no_tool_call",
                )
            if _maybe_inject_contract_gap_retry(current_step=step, trigger="no_tool_call"):
                continue
            if llm_backend == "openai_agents_sdk" and sdk_execution_state is not None:
                # SDK runner continuity can get stuck in repeated delta-mode
                # reasoning turns after a no-tool response. Reset continuity
                # cursor so the next step uses a fresh full-history turn.
                sdk_execution_state.previous_response_id = None
                sdk_execution_state.last_source_message_count = 0
                sdk_execution_state.continuation_input_items = []
                metrics["sdk_no_tool_continuity_resets"] = int(metrics.get("sdk_no_tool_continuity_resets", 0) or 0) + 1
                reset_steps = list(metrics.get("sdk_no_tool_continuity_reset_steps", []) or [])
                reset_steps.append(int(step))
                metrics["sdk_no_tool_continuity_reset_steps"] = reset_steps
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
                step += 1
                validation_retries_this_step = 0
                validation_retry_capped_this_step = False
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
        if step >= max_steps:
            if contract_retry_post_validation_pending:
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

    if contract_retry_post_validation_pending:
        _run_contract_postretry_validator(
            current_step=int(metrics.get("steps", step) or step),
            trigger="loop_exit",
        )

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
    watchdog_disable_posttask_effective = bool(loop_watchdog_decision.disable_posttask_patching) and (
        not bool(watchdog_allow_posttask_in_safe_mode)
    )
    metrics["loop_watchdog_disable_posttask_patching_effective"] = bool(watchdog_disable_posttask_effective)
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

    if posttask_learn and client is not None:
        if client is None:
            raise RuntimeError("Posttask learning requires an LLM client.")
        # Demo mode keeps Memory V2 lesson generation/promotion active while
        # suppressing legacy skill patching hooks/events for cleaner demos.
        patching_enabled = architecture_mode == "full" and not memory_v2_demo_mode and bool(skill_manifest_entries)
        if not bool(skill_manifest_entries):
            # Domains/tasks with no routed skill manifests must still run V2
            # lesson extraction/promotion; only legacy skill patching is skipped.
            metrics["posttask_skill_patching_skipped_by_mode"] = True
            metrics["posttask_skill_patching_skip_reason"] = "no_skill_manifest"
        if bool(loop_watchdog_decision) and bool(watchdog_disable_posttask_effective):
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
            unresolved_gaps=final_unresolved_gaps,
            structured_fields_required=False,
        )
        metrics["critic_raw_lessons"] = [_serialize_lesson(lesson) for lesson in lesson_result.raw_lessons]
        metrics["critic_filtered_lessons"] = [_serialize_lesson(lesson) for lesson in lesson_result.filtered_lessons]
        filtered_texts = {lesson.lesson for lesson in lesson_result.filtered_lessons}
        rejected = [lesson for lesson in lesson_result.raw_lessons if lesson.lesson not in filtered_texts]
        metrics["critic_rejected_lessons"] = [_serialize_lesson(lesson) for lesson in rejected]
        metrics["critic_generation_error"] = str(getattr(lesson_result, "error", "") or "")
        metrics["critic_generation_parsed_items"] = int(getattr(lesson_result, "parsed_items", 0) or 0)
        metrics["critic_generation_raw_chars"] = len(str(getattr(lesson_result, "raw_response_text", "") or ""))
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
            unresolved_gaps=final_unresolved_gaps,
            structured_fields_required=bool(structured_lessons_required),
        )
        metrics["v2_generation_error"] = str(getattr(v2_reflection, "error", "") or "")
        metrics["v2_generation_parsed_items"] = int(getattr(v2_reflection, "parsed_items", 0) or 0)
        metrics["v2_generation_raw_chars"] = len(str(getattr(v2_reflection, "raw_response_text", "") or ""))
        hard_events = [event for event in run_error_events if event.channel == "hard_failure"]
        fingerprint_counts = Counter(event.fingerprint for event in hard_events)
        recurring_fingerprints = [fingerprint for fingerprint, count in fingerprint_counts.items() if count >= 2]
        prioritized_fingerprints = recurring_fingerprints or [fingerprint for fingerprint, _ in fingerprint_counts.most_common(3)]
        if not repeated_error_signatures:
            repeated_error_signatures = list(recurring_fingerprints)
        v2_candidates: list[LessonRecord] = []
        structured_gap_rows = list(final_unresolved_gaps)
        structured_gap_by_signature = {
            str(row.get("gap_signature", "")).strip(): row
            for row in structured_gap_rows
            if str(row.get("gap_signature", "")).strip()
        }
        allowed_action_tools = _allowed_action_tools_for_adapter(adapter=adapter, opaque_tools=opaque_tools)
        fallback_rules: list[str] = []
        source_lesson_rows: list[dict[str, Any]] = []
        structured_model_rows_added = 0
        if structured_lessons_required and structured_gap_rows and bool(contract_gap_deterministic_recipes):
            # Deterministic fallback recipes are optional and controlled by
            # contract_gap_deterministic_recipes so benchmark arms can isolate
            # pure model-generated lesson behavior when needed.
            deterministic_rules = _deterministic_gap_fix_recipes(
                adapter=adapter,
                domain=domain,
                task_id=task_id,
                unresolved_gaps=structured_gap_rows,
                max_items=3,
            )
            for idx, recipe in enumerate(deterministic_rules):
                gap_row = structured_gap_rows[min(idx, len(structured_gap_rows) - 1)]
                source_lesson_rows.append(
                    {
                        "lesson_text": recipe,
                        "gap_row": gap_row,
                        "action_template": "",
                        "expected_evidence": "",
                        "source_kind": "deterministic",
                    }
                )
            fallback_rules = list(deterministic_rules)
            metrics["v2_structured_fallback_lessons"] = len(deterministic_rules)

        # Model lessons remain active. We append them after deterministic rows
        # so execution-critical recipes are highest-priority in retrieval.
        for idx, lesson in enumerate(v2_reflection.filtered_lessons):
            text = str(getattr(lesson, "lesson", "")).strip()
            if not text:
                continue
            if structured_lessons_required:
                valid_structured, rejection_reason, structured_payload = _validate_structured_model_lesson(
                    lesson=lesson,
                    unresolved_gap_rows=structured_gap_rows,
                    allowed_action_tools=allowed_action_tools,
                )
                if not valid_structured:
                    reason_key = str(rejection_reason).strip() or "invalid_structured_lesson"
                    metrics["v2_schema_rejection_counts"][reason_key] = int(
                        metrics["v2_schema_rejection_counts"].get(reason_key, 0)
                    ) + 1
                    continue
                trigger_signature = str(structured_payload.get("trigger_gap_signature", "")).strip()
                gap_row = structured_gap_by_signature.get(trigger_signature, {})
                action_template = str(structured_payload.get("action_template", "")).strip()
                expected_evidence = str(structured_payload.get("expected_evidence", "")).strip()
                normalized_note = " ".join(text.split()).strip()
                if normalized_note:
                    lesson_text = (
                        f"WHEN gap_signature={trigger_signature}: {action_template} "
                        f"EXPECT: {expected_evidence}. NOTE: {normalized_note}"
                    )
                else:
                    lesson_text = (
                        f"WHEN gap_signature={trigger_signature}: {action_template} "
                        f"EXPECT: {expected_evidence}."
                    )
                source_lesson_rows.append(
                    {
                        "lesson_text": lesson_text,
                        "gap_row": gap_row,
                        "action_template": action_template,
                        "expected_evidence": expected_evidence,
                        "source_kind": "model_structured",
                    }
                )
                structured_model_rows_added += 1
                continue
            gap_row = structured_gap_rows[min(idx, len(structured_gap_rows) - 1)] if structured_gap_rows else {}
            source_lesson_rows.append(
                {
                    "lesson_text": text,
                    "gap_row": gap_row,
                    "action_template": "",
                    "expected_evidence": "",
                    "source_kind": "model_legacy",
                }
            )

        if structured_lessons_required and structured_gap_rows and structured_model_rows_added == 0:
            # Backfill path: recover executable structured lessons from legacy
            # prose when strict JSON formatting fails. This keeps strict mode
            # usable without deterministic domain recipes.
            legacy_sources = list(lesson_result.filtered_lessons) + list(v2_reflection.filtered_lessons)
            backfilled_count = 0
            for idx, legacy_lesson in enumerate(legacy_sources):
                legacy_text = str(getattr(legacy_lesson, "lesson", "")).strip()
                if not legacy_text:
                    continue
                action_template = _extract_action_template_from_legacy_lesson(
                    lesson_text=legacy_text,
                    executor_tool_name=str(adapter.executor_tool_name),
                )
                if not action_template:
                    continue
                gap_row = structured_gap_rows[min(idx, len(structured_gap_rows) - 1)]
                trigger_signature = str(gap_row.get("gap_signature", "")).strip()
                reason_code = str(gap_row.get("reason_code", "")).strip()
                gap_type = str(gap_row.get("gap_type", "")).strip()
                if not (trigger_signature and reason_code and gap_type):
                    continue
                evidence = trigger_signature
                valid_backfill, _, payload = _validate_structured_model_lesson(
                    lesson=SimpleNamespace(
                        trigger_gap_signature=trigger_signature,
                        reason_code=reason_code,
                        gap_type=gap_type,
                        action_template=action_template,
                        expected_evidence=evidence,
                    ),
                    unresolved_gap_rows=structured_gap_rows,
                    allowed_action_tools=allowed_action_tools,
                )
                if not valid_backfill:
                    continue
                source_lesson_rows.append(
                    {
                        "lesson_text": (
                            f"WHEN gap_signature={payload['trigger_gap_signature']}: "
                            f"{payload['action_template']} EXPECT: {payload['expected_evidence']}."
                        ),
                        "gap_row": gap_row,
                        "action_template": str(payload["action_template"]).strip(),
                        "expected_evidence": str(payload["expected_evidence"]).strip(),
                        "source_kind": "legacy_backfill",
                    }
                )
                backfilled_count += 1
            metrics["v2_legacy_backfill_lessons"] = int(backfilled_count)

        # Deduplicate by normalized text to avoid writing noisy duplicates when
        # model output and deterministic recipe overlap semantically.
        seen_lesson_texts: set[str] = set()
        for source_row in source_lesson_rows:
            lesson_text = str(source_row.get("lesson_text", "")).strip()
            gap_row = source_row.get("gap_row", {}) if isinstance(source_row.get("gap_row", {}), dict) else {}
            action_template = str(source_row.get("action_template", "")).strip()
            expected_evidence = str(source_row.get("expected_evidence", "")).strip()
            normalized_text = " ".join(str(lesson_text).lower().split())
            if normalized_text in seen_lesson_texts:
                continue
            seen_lesson_texts.add(normalized_text)
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
                    action_template=action_template,
                    expected_evidence=expected_evidence,
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
                "action_template": row.action_template,
                "expected_evidence": row.expected_evidence,
            }
            for row in v2_candidates
        ]
        posttask_lessons_raw = {
            "raw_lessons": [_serialize_lesson(lesson) for lesson in v2_reflection.raw_lessons],
            "filtered_lessons": [_serialize_lesson(lesson) for lesson in v2_reflection.filtered_lessons],
            "fallback_rules": list(fallback_rules),
            "unresolved_gaps": list(final_unresolved_gaps),
            "generation_error": str(getattr(v2_reflection, "error", "") or ""),
            "generation_parsed_items": int(getattr(v2_reflection, "parsed_items", 0) or 0),
            "generation_raw_response": str(getattr(v2_reflection, "raw_response_text", "") or ""),
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
            same_signature_failed = False
            if current_record is not None and (
                str(current_record.reason_code).strip() or str(current_record.gap_type).strip()
            ):
                candidate_signature = str(current_record.gap_signature).strip()
                candidate_reason = str(current_record.reason_code).strip()
                if candidate_signature:
                    gap_resolved = candidate_signature not in unresolved_gap_signatures
                    same_signature_failed = not bool(gap_resolved)
                elif candidate_reason:
                    gap_resolved = candidate_reason not in unresolved_reason_codes
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
                    same_signature_failed=same_signature_failed,
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
    # Keep error_count deterministic and derived from existing primitive
    # counters at end-of-run. This avoids drift from partial increments in
    # different branches of the executor loop.
    metrics["error_count"] = (
        int(metrics.get("tool_errors", 0) or 0)
        + int(metrics.get("tool_validation_errors", 0) or 0)
        + int(metrics.get("v2_error_events", 0) or 0)
    )
    metrics["elapsed_s"] = round(time.time() - float(metrics["time_start"]), 3)

    docs_artifacts_path = write_doc_artifacts(session_dir=paths.session_dir, bundle=docs_bundle)
    learning_artifacts = {
        "contract_gap_retry": {
            "enabled": bool(contract_gap_retry),
            "steps_budget": int(contract_gap_retry_steps),
            "deterministic_recipes_enabled": bool(contract_gap_deterministic_recipes),
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
            "error_count": int(metrics.get("error_count", 0) or 0),
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
                "legacy_lessons_loaded": int(lessons_loaded),
                "legacy_lessons_text": lessons_text,
                "v2_prerun_lesson_ids": list(prerun_v2_ids),
                "v2_prerun_matches": _serialize_prerun_v2_matches(prerun_v2_matches),
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
