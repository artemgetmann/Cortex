from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class EvalJudgePhaseOutcome:
    events: list[dict[str, Any]]
    eval_result: dict[str, Any]
    probe_result: Any
    final_unresolved_gaps: list[dict[str, Any]]
    judge_input_bundle: dict[str, Any] | None
    judge_payload_bundle: dict[str, Any] | None


def run_eval_and_judge_phase(
    *,
    adapter: Any,
    has_contract: bool,
    contract_gap_retry: bool,
    contract_gap_retries_used: int,
    paths: Any,
    workspace: Any,
    task_id: str,
    task_text: str,
    domain: str,
    llm_backend: str,
    judge_diagnostic: bool,
    effective_judge_model: str,
    runtime_temperature: float | None,
    verification_spec: dict[str, Any],
    verification_spec_errors: list[str],
    client: Any | None,
    docs_judge_block: str,
    metrics: dict[str, Any],
    tasks_root: Path,
    canonicalize_hotfix_transfer_eval_events_fn: Callable[..., list[dict[str, Any]]],
    read_events_fn: Callable[[Path], list[dict[str, Any]]],
    evaluate_cli_session_fn: Callable[..., Any],
    verification_spec_for_probe_fn: Callable[[dict[str, Any]], dict[str, Any]],
    run_deterministic_probes_fn: Callable[..., Any],
    unresolved_contract_gaps_fn: Callable[[dict[str, Any]], list[dict[str, Any]]],
    llm_judge_fn: Callable[..., Any],
    clone_json_fn: Callable[[Any], Any],
    deterministic_probe_result_cls: Any,
) -> EvalJudgePhaseOutcome:
    events = read_events_fn(paths.events_path)
    probe_result = deterministic_probe_result_cls(
        source="none",
        applicable=False,
        passed=False,
        score=0.0,
        reasons=["no_verification_spec"],
        evidence={},
    )

    if has_contract:
        eval_events = canonicalize_hotfix_transfer_eval_events_fn(
            events=events,
            workspace=workspace,
            task_id=task_id,
        )
        eval_result = evaluate_cli_session_fn(
            task=task_text,
            task_id=task_id,
            events=eval_events,
            db_path=workspace.work_dir / "task.db",
            tasks_root=tasks_root,
        ).to_dict()
        probe_result = deterministic_probe_result_cls(
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
        verification_probe_spec = verification_spec_for_probe_fn(verification_spec)
        probe_result = run_deterministic_probes_fn(
            spec=verification_probe_spec,
            events=events,
            workspace=workspace,
        )
        if probe_result.applicable:
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
    final_unresolved_gaps = unresolved_contract_gaps_fn(eval_result) if has_contract else []
    metrics["contract_gap_unresolved_count_final"] = int(len(final_unresolved_gaps))
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

    use_llm_judge = bool(judge_diagnostic) or (not metrics.get("eval_passed", False))
    if not has_contract:
        if llm_backend == "anthropic":
            use_llm_judge = True
        elif not probe_result.applicable:
            use_llm_judge = True
    metrics["judge_invoked"] = bool(use_llm_judge)

    judge_input_bundle: dict[str, Any] | None = None
    judge_payload_bundle: dict[str, Any] | None = None
    if use_llm_judge:
        if client is None:
            raise RuntimeError("LLM judge requested but no LLM client is available.")
        final_state = adapter.capture_final_state(workspace)
        judge_docs_context = docs_judge_block

        def _judge_input_logger(payload: dict[str, Any]) -> None:
            nonlocal judge_input_bundle
            judge_input_bundle = clone_json_fn(payload)

        judge_result = llm_judge_fn(
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
        if not has_contract and not probe_result.applicable:
            metrics["eval_passed"] = judge_result.passed
            metrics["eval_score"] = judge_result.score
            metrics["eval_reasons"] = judge_result.reasons
            eval_result = judge_result.to_dict()

    return EvalJudgePhaseOutcome(
        events=events,
        eval_result=eval_result,
        probe_result=probe_result,
        final_unresolved_gaps=final_unresolved_gaps,
        judge_input_bundle=judge_input_bundle,
        judge_payload_bundle=judge_payload_bundle,
    )
