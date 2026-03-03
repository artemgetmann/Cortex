from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class ContractGapRetryState:
    """Mutable state for deterministic contract-gap retry orchestration.

    This is intentionally explicit so runtime loop code can pass one object
    around instead of mutating multiple nonlocal variables.
    """

    contract_gap_retries_used: int = 0
    contract_gap_prestop_artifacts: list[str] = field(default_factory=list)
    latest_unresolved_gaps: list[dict[str, Any]] = field(default_factory=list)
    contract_retry_validator_sql: str = ""
    contract_retry_validator_query_ids: list[str] = field(default_factory=list)
    contract_retry_post_validation_pending: bool = False
    contract_retry_repair_observed: bool = False


def maybe_inject_contract_gap_retry(
    *,
    state: ContractGapRetryState,
    current_step: int,
    trigger: str,
    has_contract: bool,
    contract_gap_retry: bool,
    contract_gap_retry_steps: int,
    contract_gap_deterministic_recipes: bool,
    task_text: str,
    task_id: str,
    domain: str,
    benchmark_placebo: bool,
    structured_lessons_required: bool,
    enable_transfer_retrieval: bool,
    transfer_retrieval_policy: dict[str, Any] | None,
    transfer_retrieval_max_results: int,
    transfer_retrieval_score_weight: float,
    runtime_candidate_policy_effective: str,
    lessons_v2_path: Path,
    tasks_root: Path,
    adapter: Any,
    workspace: Any,
    paths: Any,
    metrics: dict[str, Any],
    messages: list[dict[str, Any]],
    lesson_activation_records: list[dict[str, Any]],
    on_lifecycle_event: Callable[[str, dict[str, Any]], None] | None,
    verbose: bool,
    canonicalize_hotfix_transfer_eval_events_fn: Callable[..., list[dict[str, Any]]],
    read_events_fn: Callable[[Path], list[dict[str, Any]]],
    evaluate_cli_session_fn: Callable[..., Any],
    unresolved_contract_gaps_fn: Callable[[dict[str, Any]], list[dict[str, Any]]],
    run_shell_hotfix_transfer_closure_check_fn: Callable[..., dict[str, Any]],
    write_event_fn: Callable[[Path, dict[str, Any]], None],
    clip_text_fn: Callable[[str], str],
    adaptive_gap_lesson_cap_fn: Callable[..., int],
    retrieve_on_error_fn: Callable[..., tuple[list[Any], Any]],
    select_gap_targeted_matches_fn: Callable[..., list[Any]],
    placebo_hint_for_lesson_fn: Callable[..., str],
    deterministic_gap_fix_recipes_fn: Callable[..., list[str]],
    format_contract_gap_retry_prompt_fn: Callable[..., str],
) -> bool:
    if (
        not has_contract
        or not bool(contract_gap_retry)
        or state.contract_gap_retries_used >= int(contract_gap_retry_steps)
    ):
        return False

    prestop_events = canonicalize_hotfix_transfer_eval_events_fn(
        events=read_events_fn(paths.events_path),
        workspace=workspace,
        task_id=task_id,
    )
    prestop_eval = evaluate_cli_session_fn(
        task=task_text,
        task_id=task_id,
        events=prestop_events,
        db_path=workspace.work_dir / "task.db",
        tasks_root=tasks_root,
    ).to_dict()
    unresolved_gaps = unresolved_contract_gaps_fn(prestop_eval)
    validator_evidence: list[str] = []

    closure_check = run_shell_hotfix_transfer_closure_check_fn(
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
        write_event_fn(
            paths.events_path,
            {
                "step": current_step,
                "tool": "contract_closure_check",
                "tool_input": {
                    "task_id": task_id,
                    "attempt": state.contract_gap_retries_used + 1,
                },
                "ok": bool(closure_check.get("passed", False)),
                "error": None if bool(closure_check.get("passed", False)) else "closure_gaps_detected",
                "output": json.dumps(closure_check, ensure_ascii=True),
            },
        )

    state.latest_unresolved_gaps = unresolved_gaps
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
    state.latest_unresolved_gaps = unresolved_gaps
    metrics["contract_gap_unresolved_count_prestop"] = int(len(unresolved_gaps))
    prestop_artifact_path = paths.session_dir / f"contract_gap_prestop_attempt_{state.contract_gap_retries_used + 1}.json"
    prestop_artifact_path.write_text(
        json.dumps(
            {
                "step": current_step,
                "attempt": state.contract_gap_retries_used + 1,
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
    state.contract_gap_prestop_artifacts.append(str(prestop_artifact_path))
    if not unresolved_gaps:
        return False

    metrics["contract_gap_retry_attempts"] = int(metrics.get("contract_gap_retry_attempts", 0) or 0) + 1
    metrics["contract_gap_retry_triggered"] = int(metrics.get("contract_gap_retry_triggered", 0) or 0) + 1
    state.contract_gap_retries_used += 1
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

    state.contract_retry_validator_sql = ""
    state.contract_retry_validator_query_ids = []
    state.contract_retry_post_validation_pending = False
    state.contract_retry_repair_observed = False
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
                state.contract_retry_validator_sql = validator_sql
                state.contract_retry_validator_query_ids = list(query_ids)
                state.contract_retry_post_validation_pending = True
                validator_result = adapter.execute(
                    adapter.executor_tool_name,
                    {"sql": validator_sql},
                    workspace,
                )
                metrics["contract_validator_runs"] = int(metrics.get("contract_validator_runs", 0) or 0) + 1
                metrics["contract_validator_query_ids"] = query_ids
                metrics["contract_validator_last_status"] = "ok" if not validator_result.is_error() else "error"
                write_event_fn(
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
                    validator_evidence.append(clip_text_fn(str(validator_result.output)))
                if validator_result.error:
                    validator_evidence.append(f"validator_error={clip_text_fn(str(validator_result.error))}")

    gap_cap = adaptive_gap_lesson_cap_fn(unresolved_gaps=unresolved_gaps, min_cap=1, max_cap=3)
    gap_matches, _ = retrieve_on_error_fn(
        path=lessons_v2_path,
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
    gap_matches = select_gap_targeted_matches_fn(
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
            placebo_hint_for_lesson_fn(lesson_id=lesson_id, task_id=task_id, domain=domain)
            if benchmark_placebo
            else str(getattr(lesson, "rule_text", "")).strip()
        )
        if hint_text:
            gap_hints.append(hint_text)
    deterministic_gap_hints = (
        deterministic_gap_fix_recipes_fn(
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
    retry_prompt = format_contract_gap_retry_prompt_fn(
        unresolved_gaps=unresolved_gaps,
        deterministic_recipes=deterministic_gap_hints,
        injected_hints=gap_hints,
        validator_evidence=validator_evidence,
    )
    messages.append({"role": "user", "content": [{"type": "text", "text": retry_prompt}]})
    write_event_fn(
        paths.events_path,
        {
            "step": current_step,
            "tool": "contract_gap_retry",
            "tool_input": {
                "attempt": state.contract_gap_retries_used,
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


def run_contract_postretry_validator(
    *,
    state: ContractGapRetryState,
    current_step: int,
    trigger: str,
    adapter: Any,
    workspace: Any,
    paths: Any,
    metrics: dict[str, Any],
    write_event_fn: Callable[[Path, dict[str, Any]], None],
) -> None:
    if not state.contract_retry_post_validation_pending:
        return
    validator_sql = str(state.contract_retry_validator_sql or "").strip()
    if not validator_sql:
        state.contract_retry_post_validation_pending = False
        return
    validator_result = adapter.execute(
        adapter.executor_tool_name,
        {"sql": validator_sql},
        workspace,
    )
    metrics["contract_validator_postretry_runs"] = int(metrics.get("contract_validator_postretry_runs", 0) or 0) + 1
    metrics["contract_validator_postretry_last_status"] = "ok" if not validator_result.is_error() else "error"
    metrics["contract_validator_postretry_last_trigger"] = str(trigger)
    metrics["contract_retry_repair_observed"] = bool(state.contract_retry_repair_observed)
    write_event_fn(
        paths.events_path,
        {
            "step": current_step,
            "tool": "contract_validator_postretry",
            "tool_input": {
                "query_ids": list(state.contract_retry_validator_query_ids),
                "sql": validator_sql,
                "trigger": trigger,
                "repair_observed": bool(state.contract_retry_repair_observed),
            },
            "ok": not validator_result.is_error(),
            "error": validator_result.error,
            "output": validator_result.output,
        },
    )
    state.contract_retry_post_validation_pending = False

