from __future__ import annotations

from tracks.cli_sqlite import agent_cli as _agent_cli
from tracks.cli_sqlite.agent_runtime_loop_impl import _run_cli_agent_impl_extracted

_RUNTIME_LOOP_LOCAL_SYMBOLS = {
    "_agent_cli",
    "_RUNTIME_LOOP_LOCAL_SYMBOLS",
    "_sync_runtime_symbols",
    "prepare_cli_prompt_preview",
    "run_cli_agent",
    "_run_cli_agent_impl",
    "_run_cli_agent_impl_extracted",
}


def _sync_runtime_symbols() -> None:
    """Mirror agent_cli globals so test monkeypatching remains behavior-compatible."""
    for _name, _value in vars(_agent_cli).items():
        if _name.startswith("__"):
            continue
        if _name in _RUNTIME_LOOP_LOCAL_SYMBOLS:
            continue
        globals()[_name] = _value


_sync_runtime_symbols()

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
    """Build the exact prompt/tools payload without executing a session."""
    _sync_runtime_symbols()
    # Workstream 1 only introduces mode plumbing; strict/legacy behavior split lands
    # in later workstreams but this keeps preview and runtime signatures aligned.
    learning_mode = _normalize_learning_mode(learning_mode)
    executor_prompt_mode = _normalize_executor_prompt_mode(executor_prompt_mode)
    adapter = _resolve_adapter_with_mode(
        domain,
        cryptic_errors=cryptic_errors,
        semi_helpful_errors=semi_helpful_errors,
        mixed_errors=mixed_errors,
    )
    runtime_contract: dict[str, Any] | None = None
    try:
        # Preview path uses task-level contract only (no session runtime
        # override), which is still enough for deterministic checklist hints.
        runtime_contract, _ = load_contract(TASKS_ROOT, task_id)
    except Exception:
        runtime_contract = None
    normalized_doc_mode = normalize_doc_mode(doc_mode)
    normalized_doc_retrieval = normalize_doc_retrieval_mode(doc_retrieval)
    task_dir = TASKS_ROOT / task_id
    if not task_dir.exists():
        raise FileNotFoundError(f"Unknown task id: {task_id!r} (missing {task_dir})")
    fixture_refs = sorted(p.name for p in task_dir.glob("*.csv"))
    if (task_dir / "task.md").exists():
        fixture_refs.append("task.md")
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
        fixture_refs=fixture_refs,
        bootstrap=bootstrap,
        require_skill_read=require_skill_read,
        opaque_tools=opaque_tools,
        legacy_lessons_enabled=True,
        benchmark_placebo=False,
        runtime_candidate_policy_effective=DEFAULT_RUNTIME_CANDIDATE_POLICY,
        runtime_contract=runtime_contract,
        llm_client=None,
        documentation=documentation,
        doc_mode=normalized_doc_mode,
        doc_retrieval=normalized_doc_retrieval,
        doc_budget_tokens=int(doc_budget_tokens),
        doc_retriever_model=doc_retriever_model,
        preload_docs_bundle=bool(executor_docs and normalized_doc_mode != "none"),
        executor_docs=executor_docs,
        judge_docs=False,
        docs_prompt_max_chars=8000,
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

    return CliPromptPreview(
        task_text=prompt_context.task_text,
        system_prompt=prompt_context.system_prompt,
        lessons_text=prompt_context.lessons_text,
        tools=prompt_context.tools,
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
    _sync_runtime_symbols()
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
            executor_prompt_mode=executor_prompt_mode,
            judge_diagnostic=judge_diagnostic,
            contract_gap_retry=contract_gap_retry,
            contract_gap_retry_steps=contract_gap_retry_steps,
            contract_gap_deterministic_recipes=contract_gap_deterministic_recipes,
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
            watchdog_allow_posttask_in_safe_mode=watchdog_allow_posttask_in_safe_mode,
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
    kwargs = dict(locals())
    return _run_cli_agent_impl_extracted(runtime_symbols=globals(), **kwargs)
