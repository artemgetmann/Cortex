from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class VerifierWatchdogOutcome:
    repeated_error_signatures: list[str]
    loop_watchdog_decision: Any
    loop_watchdog_safe_mode_active: bool
    loop_watchdog_failure_signals: list[str]
    loop_watchdog_stop_flag: bool
    effective_self_edit_mode_active: bool
    watchdog_disable_posttask_effective: bool


def run_verifier_and_watchdog_phase(
    *,
    has_contract: bool,
    verifier_stack_enabled: bool,
    low_confidence_threshold: float,
    clarify_on_low_confidence: bool,
    max_low_confidence_probes: int,
    task_id: str,
    domain: str,
    workspace: Any,
    verification_spec: dict[str, Any],
    events: list[dict[str, Any]],
    eval_result: dict[str, Any],
    probe_result: Any,
    final_unresolved_gaps: list[dict[str, Any]],
    run_error_events: list[Any],
    loop_watchdog_state: Any,
    loop_watchdog_state_path: Path,
    posttask_learn: bool,
    self_edit_mode_active: bool,
    watchdog_allow_posttask_in_safe_mode: bool,
    run_id: str | None,
    session_id: int,
    learning_mode: str,
    sessions_root: Path,
    metrics: dict[str, Any],
    paths: Any,
    on_lifecycle_event: Callable[[str, dict[str, Any]], None] | None,
    clamp_fn: Callable[[float, float, float], float],
    dedupe_nonempty_text_rows_fn: Callable[[list[str]], list[str]],
    collect_event_text_blobs_fn: Callable[[list[dict[str, Any]]], str],
    run_required_files_probe_fn: Callable[..., dict[str, Any]],
    normalize_required_file_content_patterns_fn: Callable[..., list[dict[str, Any]]],
    run_required_file_content_patterns_probe_fn: Callable[..., dict[str, Any]],
    normalize_required_queries_fn: Callable[..., list[dict[str, Any]]],
    resolve_verification_db_path_fn: Callable[..., Path],
    run_required_query_probe_fn: Callable[..., dict[str, Any]],
    run_sqlite_gap_query_probe_fn: Callable[..., dict[str, Any]],
    build_low_confidence_clarifying_question_fn: Callable[..., str],
    write_event_fn: Callable[[Path, dict[str, Any]], None],
    evaluate_watchdog_policy_fn: Callable[..., Any],
    loop_watchdog_snapshot_cls: Any,
    append_self_edit_gate_event_fn: Callable[..., None],
) -> VerifierWatchdogOutcome:
    confidence_base = float(metrics.get("eval_score", 0.0) or 0.0)
    if not has_contract and metrics.get("judge_score") is not None:
        try:
            confidence_base = float(metrics.get("judge_score", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence_base = float(metrics.get("eval_score", 0.0) or 0.0)
    confidence_base = clamp_fn(confidence_base, 0.0, 1.0)
    metrics["verifier_confidence_base"] = round(confidence_base, 4)
    low_confidence_triggered = bool(verifier_stack_enabled) and confidence_base < float(low_confidence_threshold)
    metrics["verifier_low_confidence_triggered"] = bool(low_confidence_triggered)

    if low_confidence_triggered:
        probe_rows: list[dict[str, Any]] = []
        missing_verification_lines: list[str] = []

        required_verification_lines = dedupe_nonempty_text_rows_fn(
            [str(value) for value in (verification_spec.get("exact_output_lines", []) or [])]
        )
        if required_verification_lines and len(probe_rows) < max_low_confidence_probes:
            event_text = collect_event_text_blobs_fn(events)
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

        required_files = dedupe_nonempty_text_rows_fn(
            [str(value) for value in (verification_spec.get("required_files", []) or [])]
        )
        if required_files and len(probe_rows) < max_low_confidence_probes:
            probe_rows.append(
                run_required_files_probe_fn(
                    work_dir=workspace.work_dir,
                    required_files=required_files,
                )
            )

        required_file_content_patterns = normalize_required_file_content_patterns_fn(
            verification_spec.get("required_file_content_patterns", [])
        )
        if required_file_content_patterns and len(probe_rows) < max_low_confidence_probes:
            probe_rows.append(
                run_required_file_content_patterns_probe_fn(
                    work_dir=workspace.work_dir,
                    required_file_content_patterns=required_file_content_patterns,
                )
            )

        required_queries = normalize_required_queries_fn(verification_spec.get("required_queries", []))
        if required_queries:
            default_query_db_path = resolve_verification_db_path_fn(
                work_dir=workspace.work_dir,
                db_path_hint=str(verification_spec.get("db_path", "")).strip(),
            )
            for query_spec in required_queries:
                if len(probe_rows) >= max_low_confidence_probes:
                    break
                query_db_path = resolve_verification_db_path_fn(
                    work_dir=workspace.work_dir,
                    db_path_hint=str(query_spec.get("db_path", "")).strip() or str(default_query_db_path),
                )
                probe_rows.append(
                    run_required_query_probe_fn(
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
                    run_sqlite_gap_query_probe_fn(
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
            clarifying_question = build_low_confidence_clarifying_question_fn(
                task_id=task_id,
                missing_verification_lines=missing_verification_lines,
                unresolved_gaps=final_unresolved_gaps,
            )
            metrics["verifier_clarifying_question"] = clarifying_question
            write_event_fn(
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

    hard_failure_counts = Counter(
        event.fingerprint for event in run_error_events if event.channel == "hard_failure"
    )
    repeated_error_signatures = sorted(
        fingerprint
        for fingerprint, count in hard_failure_counts.items()
        if count >= 2
    )
    loop_watchdog_snapshot = loop_watchdog_snapshot_cls(
        repeated_hard_failure_signatures=len(repeated_error_signatures),
        contract_gap_unresolved_count=len(final_unresolved_gaps),
        rejection_streak=int(loop_watchdog_state.rejection_streak),
    )
    loop_watchdog_decision = evaluate_watchdog_policy_fn(
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
        write_event_fn(
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
        append_self_edit_gate_event_fn(
            sessions_root=sessions_root,
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

    return VerifierWatchdogOutcome(
        repeated_error_signatures=repeated_error_signatures,
        loop_watchdog_decision=loop_watchdog_decision,
        loop_watchdog_safe_mode_active=loop_watchdog_safe_mode_active,
        loop_watchdog_failure_signals=loop_watchdog_failure_signals,
        loop_watchdog_stop_flag=loop_watchdog_stop_flag,
        effective_self_edit_mode_active=effective_self_edit_mode_active,
        watchdog_disable_posttask_effective=watchdog_disable_posttask_effective,
    )
