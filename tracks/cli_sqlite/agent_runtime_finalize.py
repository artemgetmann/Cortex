from __future__ import annotations

import json
import time
from collections import Counter
from typing import Any, Mapping


def finalize_runtime_run(
    *,
    metrics: dict[str, Any],
    loop_watchdog_decision: Any | None,
    loop_watchdog_state: Any,
    loop_watchdog_state_path: Any,
    run_id: str | None,
    final_unresolved_gaps: list[dict[str, Any]],
    repeated_error_signatures: list[str],
    run_error_events: list[Any],
    escalation_state: dict[str, Any],
    model_critic: str,
    auto_escalate_critic: bool,
    escalation_score_threshold: float,
    escalation_consecutive_runs: int,
    critic_no_updates: bool,
    paths: Any,
    docs_bundle: Any,
    doc_mode: str,
    docs_executor_block: str,
    docs_judge_block: str,
    docs_selected_source_ids: list[str],
    doc_retrieval: str,
    system_prompt: str,
    task_text: str,
    lessons_loaded: int,
    lessons_text: str,
    prerun_v2_ids: list[str],
    prerun_v2_matches: list[Any],
    routed_refs: list[str],
    required_skill_refs: set[str],
    routed_entries: list[Any],
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    executor_input_bundles: list[dict[str, Any]],
    judge_input_bundle: dict[str, Any] | None,
    judge_payload_bundle: dict[str, Any] | None,
    effective_judge_model: str,
    v2_candidate_lessons: list[dict[str, Any]],
    promoted_lesson_ids: list[str],
    suppressed_lesson_ids: list[str],
    deps: Mapping[str, Any],
) -> Any:
    # Resolve helper symbols from runtime module so behavior remains identical.
    _sum_rejection_counts = deps["_sum_rejection_counts"]
    LoopWatchdogDecision = deps["LoopWatchdogDecision"]
    next_watchdog_state = deps["next_watchdog_state"]
    persist_watchdog_state = deps["persist_watchdog_state"]
    _escalate_if_needed = deps["_escalate_if_needed"]
    _save_escalation_state = deps["_save_escalation_state"]
    write_doc_artifacts = deps["write_doc_artifacts"]
    _serialize_prerun_v2_matches = deps["_serialize_prerun_v2_matches"]
    _clone_json = deps["_clone_json"]
    write_metrics = deps["write_metrics"]
    CliRunResult = deps["CliRunResult"]

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
            "enabled": bool(metrics.get("contract_gap_retry", False)),
            "steps_budget": int(metrics.get("contract_gap_retry_steps", 0) or 0),
            "deterministic_recipes_enabled": bool(metrics.get("contract_gap_deterministic_recipes", False)),
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
