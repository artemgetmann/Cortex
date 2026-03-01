#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from config import load_config
from tracks.cli_sqlite.agent_cli import (
    ARCHITECTURE_MODES,
    DEFAULT_CRITIC_MODEL,
    DEFAULT_ARCHITECTURE_MODE,
    DEFAULT_DOC_BUDGET_TOKENS,
    DEFAULT_DOC_MODE,
    DEFAULT_DOC_RETRIEVAL_MODE,
    DEFAULT_EXECUTOR_MODEL,
    DEFAULT_EXECUTOR_PROMPT_MODE,
    DEFAULT_CONTRACT_GAP_RETRY,
    DEFAULT_CONTRACT_GAP_RETRY_STEPS,
    DEFAULT_CONTRACT_GAP_DETERMINISTIC_RECIPES,
    DEFAULT_WATCHDOG_ALLOW_POSTTASK_IN_SAFE_MODE,
    DEFAULT_VERIFIER_STACK_ENABLED,
    DEFAULT_LOW_CONFIDENCE_THRESHOLD,
    DEFAULT_CLARIFY_ON_LOW_CONFIDENCE,
    DEFAULT_MAX_LOW_CONFIDENCE_PROBES,
    DEFAULT_LLM_BACKEND,
    DEFAULT_LEARNING_MODE,
    DEFAULT_BENCHMARK_DETERMINISTIC,
    DEFAULT_BENCHMARK_PLACEBO,
    DEFAULT_BENCHMARK_PROMOTED_ONLY,
    DEFAULT_SELF_EDIT_MODE,
    DEFAULT_STRUCTURED_LESSONS_REQUIRED,
    DEFAULT_TRANSFER_RETRIEVAL_MAX_RESULTS,
    DEFAULT_TRANSFER_RETRIEVAL_SCORE_WEIGHT,
    LLM_BACKENDS,
    OPENAI_DEFAULT_MODEL,
    LEARNING_MODES,
    run_cli_agent,
)
from tracks.cli_sqlite import run_service


class _RunCancelled(RuntimeError):
    """Raised when an external transport requests cancellation mid-run."""


COST_PROFILES = ("default", "cheap")
CHEAP_EXECUTOR_MODEL = "claude-3-haiku-20240307"

def _cli_flag_provided(flag: str) -> bool:
    return any(arg == flag or arg.startswith(f"{flag}=") for arg in sys.argv[1:])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--task", default="")
    ap.add_argument("--session", required=True, type=int)
    ap.add_argument(
        "--run-id",
        default="",
        help="Optional externally supplied run id. If omitted, run service generates one.",
    )
    ap.add_argument("--max-steps", type=int, default=12)
    ap.add_argument("--domain", default="sqlite", choices=["sqlite", "gridtool", "fluxtool", "artic", "shell"],
                     help="Domain adapter to use (default: sqlite)")
    ap.add_argument("--learning-mode", default=DEFAULT_LEARNING_MODE, choices=LEARNING_MODES)
    ap.add_argument("--architecture-mode", default=DEFAULT_ARCHITECTURE_MODE, choices=ARCHITECTURE_MODES)
    ap.add_argument("--model-executor", default=DEFAULT_EXECUTOR_MODEL)
    ap.add_argument("--model-critic", default=DEFAULT_CRITIC_MODEL)
    ap.add_argument("--model-judge", default=None,
                     help="Model for LLM judge (default: one tier above executor)")
    ap.add_argument("--auto-escalate-critic", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--escalation-score-threshold", type=float, default=0.75)
    ap.add_argument("--escalation-consecutive-runs", type=int, default=2)
    ap.add_argument("--require-skill-read", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--posttask-mode", choices=["candidate", "direct"], default="candidate")
    ap.add_argument("--no-posttask-learn", action="store_true")
    ap.add_argument(
        "--self-edit-mode",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_SELF_EDIT_MODE,
        help="Enable guarded orchestration self-edit gate (whitelisted files + verification checks).",
    )
    ap.add_argument(
        "--memory-v2-demo-mode",
        action="store_true",
        help="Suppress legacy posttask_hook/promotion_gate skill patching while keeping Memory V2 active",
    )
    ap.add_argument("--opaque-tools", action="store_true", help="Use opaque tool names to test skill-reading behavior")
    ap.add_argument("--bootstrap", action="store_true",
                     help="Bootstrap mode: no skill docs, agent learns from scratch via lessons only")
    ap.add_argument("--cryptic-errors", action="store_true",
                     help="Cryptic error mode: strip helpful hints from tool error messages")
    ap.add_argument("--semi-helpful-errors", action="store_true",
                     help="Semi-helpful error mode: hint at fixes without full syntax")
    ap.add_argument("--mixed-errors", action="store_true",
                     help="Mixed mode: semi-helpful for simple commands, cryptic for core pipeline commands")
    ap.add_argument(
        "--enable-transfer-retrieval",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable cross-domain transfer lane for on-error Memory V2 retrieval",
    )
    ap.add_argument(
        "--transfer-retrieval-max-results",
        type=int,
        default=DEFAULT_TRANSFER_RETRIEVAL_MAX_RESULTS,
        help="Maximum transfer-lane hints per failed step",
    )
    ap.add_argument(
        "--transfer-retrieval-score-weight",
        type=float,
        default=DEFAULT_TRANSFER_RETRIEVAL_SCORE_WEIGHT,
        help="Score multiplier applied to transfer-lane candidates",
    )
    ap.add_argument(
        "--llm-backend",
        default=DEFAULT_LLM_BACKEND,
        choices=LLM_BACKENDS,
        help="Executor transport: anthropic (API), claude_print (`claude -p`), or openai (Chat Completions API).",
    )
    ap.add_argument(
        "--cost-profile",
        default="default",
        choices=COST_PROFILES,
        help="Cost preset. cheap pins executor/judge to Claude 3 Haiku and disables judge diagnostics.",
    )
    ap.add_argument(
        "--documentation",
        action="append",
        default=[],
        help="Path or URL to documentation source (repeatable).",
    )
    ap.add_argument(
        "--doc-mode",
        default=DEFAULT_DOC_MODE,
        choices=["none", "lossy", "full"],
        help="Documentation context mode.",
    )
    ap.add_argument(
        "--doc-budget-tokens",
        type=int,
        default=DEFAULT_DOC_BUDGET_TOKENS,
        help="Budget for lossy/full documentation brief.",
    )
    ap.add_argument(
        "--doc-retrieval",
        default=DEFAULT_DOC_RETRIEVAL_MODE,
        choices=["off", "auto"],
        help="Documentation retrieval strategy.",
    )
    ap.add_argument(
        "--doc-retriever-model",
        default="",
        help="Optional model for doc distillation in auto retrieval mode.",
    )
    ap.add_argument(
        "--judge-docs",
        default="off",
        choices=["on", "off"],
        help="Whether to provide docs context to the judge.",
    )
    ap.add_argument(
        "--executor-docs",
        default="off",
        choices=["on", "off"],
        help="Whether to provide docs context to the executor prompt.",
    )
    ap.add_argument(
        "--executor-prompt-mode",
        default=DEFAULT_EXECUTOR_PROMPT_MODE,
        choices=["full", "minimal"],
        help="Executor system prompt mode: full keeps domain fragments, minimal uses generic tool-first prompt.",
    )
    ap.add_argument(
        "--judge-diagnostic",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Run LLM judge even when deterministic contract passes (diagnostic-only; contract remains primary).",
    )
    ap.add_argument(
        "--contract-gap-retry",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_CONTRACT_GAP_RETRY,
        help="Before stop, run deterministic contract-gap check and inject one targeted retry.",
    )
    ap.add_argument(
        "--contract-gap-retry-steps",
        type=int,
        default=DEFAULT_CONTRACT_GAP_RETRY_STEPS,
        help="Maximum targeted retries from contract-gap checker (currently capped to 1).",
    )
    ap.add_argument(
        "--contract-gap-deterministic-recipes",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_CONTRACT_GAP_DETERMINISTIC_RECIPES,
        help="Enable adapter-provided deterministic repair recipes during contract-gap retry prompts.",
    )
    ap.add_argument(
        "--structured-lessons-required",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_STRUCTURED_LESSONS_REQUIRED,
        help="Require V2 candidates to include reason_code + gap_type metadata.",
    )
    ap.add_argument(
        "--verifier-stack",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_VERIFIER_STACK_ENABLED,
        help="Enable deterministic low-confidence verifier stack (probes + optional clarify prompt).",
    )
    ap.add_argument(
        "--low-confidence-threshold",
        type=float,
        default=DEFAULT_LOW_CONFIDENCE_THRESHOLD,
        help="Trigger deterministic probes when eval confidence drops below this threshold.",
    )
    ap.add_argument(
        "--clarify-on-low-confidence",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_CLARIFY_ON_LOW_CONFIDENCE,
        help="Emit deterministic clarification question when low-confidence probes are inconclusive.",
    )
    ap.add_argument(
        "--max-low-confidence-probes",
        type=int,
        default=DEFAULT_MAX_LOW_CONFIDENCE_PROBES,
        help="Maximum deterministic probes to run when low-confidence verifier stack triggers.",
    )
    ap.add_argument(
        "--benchmark-deterministic",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_BENCHMARK_DETERMINISTIC,
        help="Force deterministic benchmark settings (temperature=0 for executor/judge/lesson generation).",
    )
    ap.add_argument(
        "--benchmark-promoted-only",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_BENCHMARK_PROMOTED_ONLY,
        help="Restrict retrieval to promoted lessons only (exclude candidates).",
    )
    ap.add_argument(
        "--benchmark-placebo",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_BENCHMARK_PLACEBO,
        help="Keep retrieval structure but replace injected lesson text with deterministic generic placebo hints.",
    )
    ap.add_argument(
        "--watchdog-allow-posttask-in-safe-mode",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_WATCHDOG_ALLOW_POSTTASK_IN_SAFE_MODE,
        help="Allow posttask learning writes even when loop watchdog enters safe mode (benchmark override).",
    )
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    effective_backend = args.llm_backend
    default_executor_model = OPENAI_DEFAULT_MODEL if effective_backend == "openai" else DEFAULT_EXECUTOR_MODEL
    default_critic_model = OPENAI_DEFAULT_MODEL if effective_backend == "openai" else DEFAULT_CRITIC_MODEL
    effective_executor_model = (
        (args.model_executor.strip() or default_executor_model)
        if _cli_flag_provided("--model-executor")
        else default_executor_model
    )
    effective_critic_model = (
        (args.model_critic.strip() or default_critic_model)
        if _cli_flag_provided("--model-critic")
        else default_critic_model
    )
    if _cli_flag_provided("--model-judge"):
        effective_judge_model = args.model_judge.strip() if args.model_judge else None
    elif effective_backend == "openai":
        effective_judge_model = effective_executor_model
    else:
        effective_judge_model = None
    effective_judge_diagnostic = bool(args.judge_diagnostic)
    if args.cost_profile == "cheap":
        effective_executor_model = CHEAP_EXECUTOR_MODEL
        effective_critic_model = CHEAP_EXECUTOR_MODEL
        effective_judge_model = CHEAP_EXECUTOR_MODEL
        effective_backend = "anthropic"
        effective_judge_diagnostic = False

    try:
        cfg = load_config()
    except RuntimeError:
        # Non-Anthropic transports can run without ANTHROPIC_API_KEY.
        if effective_backend in {"claude_print", "openai"}:
            cfg = SimpleNamespace(anthropic_api_key="")
        else:
            raise

    run_record = run_service.start_run(
        task_id=args.task_id,
        domain=args.domain,
        session_id=args.session,
        run_id=str(args.run_id).strip() or None,
        metadata={
            "source": "run_cli_agent.py",
            "max_steps": int(args.max_steps),
            "llm_backend": str(effective_backend),
            "cost_profile": str(args.cost_profile),
            "self_edit_mode": bool(args.self_edit_mode),
        },
    )

    def _on_step(step: int, tool: str, ok: bool, error: str | None) -> None:
        # Heartbeats keep run status observable for transports polling by run_id.
        run_service.mark_heartbeat(run_record.run_id, last_step=step)
        if run_service.is_cancel_requested(run_record.run_id):
            raise _RunCancelled(
                f"Run {run_record.run_id} cancelled at step {step} while executing {tool} (ok={ok}): {error or ''}"
            )

    if run_service.is_cancel_requested(run_record.run_id):
        run_service.update_run(
            run_record.run_id,
            status=run_service.STATUS_CANCELLED,
            cancel_requested=True,
            error=f"Run {run_record.run_id} cancelled before execution started.",
        )
        print(json_dump({"run_id": run_record.run_id, "cancelled": True, "session_id": args.session}))
        return 1

    try:
        result = run_cli_agent(
            cfg=cfg,
            task_id=args.task_id,
            task=args.task or None,
            session_id=args.session,
            max_steps=args.max_steps,
            domain=args.domain,
            learning_mode=args.learning_mode,
            architecture_mode=args.architecture_mode,
            model_executor=effective_executor_model,
            model_critic=effective_critic_model,
            model_judge=effective_judge_model,
            posttask_mode=args.posttask_mode,
            posttask_learn=not args.no_posttask_learn,
            self_edit_mode=bool(args.self_edit_mode),
            memory_v2_demo_mode=bool(args.memory_v2_demo_mode),
            verbose=args.verbose,
            auto_escalate_critic=bool(args.auto_escalate_critic),
            escalation_score_threshold=args.escalation_score_threshold,
            escalation_consecutive_runs=max(1, args.escalation_consecutive_runs),
            require_skill_read=bool(args.require_skill_read) and not args.bootstrap,
            opaque_tools=bool(args.opaque_tools),
            bootstrap=bool(args.bootstrap),
            cryptic_errors=bool(args.cryptic_errors),
            semi_helpful_errors=bool(args.semi_helpful_errors),
            mixed_errors=bool(args.mixed_errors),
            enable_transfer_retrieval=bool(args.enable_transfer_retrieval),
            transfer_retrieval_max_results=max(0, int(args.transfer_retrieval_max_results)),
            transfer_retrieval_score_weight=max(0.0, float(args.transfer_retrieval_score_weight)),
            documentation=[str(item).strip() for item in args.documentation if str(item).strip()],
            doc_mode=args.doc_mode,
            doc_budget_tokens=max(128, int(args.doc_budget_tokens)),
            doc_retrieval=args.doc_retrieval,
            doc_retriever_model=str(args.doc_retriever_model).strip() or None,
            judge_docs=args.judge_docs == "on",
            executor_docs=args.executor_docs == "on",
            executor_prompt_mode=args.executor_prompt_mode,
            judge_diagnostic=effective_judge_diagnostic,
            contract_gap_retry=bool(args.contract_gap_retry),
            contract_gap_retry_steps=max(0, int(args.contract_gap_retry_steps)),
            contract_gap_deterministic_recipes=bool(args.contract_gap_deterministic_recipes),
            structured_lessons_required=bool(args.structured_lessons_required),
            verifier_stack_enabled=bool(args.verifier_stack),
            low_confidence_threshold=max(0.0, min(1.0, float(args.low_confidence_threshold))),
            clarify_on_low_confidence=bool(args.clarify_on_low_confidence),
            max_low_confidence_probes=max(1, int(args.max_low_confidence_probes)),
            llm_backend=effective_backend,
            benchmark_deterministic=bool(args.benchmark_deterministic),
            benchmark_promoted_only=bool(args.benchmark_promoted_only),
            benchmark_placebo=bool(args.benchmark_placebo),
            watchdog_allow_posttask_in_safe_mode=bool(args.watchdog_allow_posttask_in_safe_mode),
            on_step=_on_step,
        )
    except _RunCancelled as exc:
        run_service.update_run(
            run_record.run_id,
            status=run_service.STATUS_CANCELLED,
            cancel_requested=True,
            error=str(exc),
            result={"cancelled": True, "session_id": args.session},
        )
        print(json_dump({"run_id": run_record.run_id, "cancelled": True, "session_id": args.session}))
        return 1
    except Exception as exc:
        run_service.update_run(
            run_record.run_id,
            status=run_service.STATUS_FAILED,
            error=str(exc),
            result={"session_id": args.session},
        )
        raise

    result.metrics["run_id"] = run_record.run_id
    if run_service.is_cancel_requested(run_record.run_id):
        run_service.update_run(
            run_record.run_id,
            status=run_service.STATUS_CANCELLED,
            cancel_requested=True,
            result={"session_id": args.session, "metrics": result.metrics},
        )
        print(json_dump(result.metrics))
        return 1

    run_service.update_run(
        run_record.run_id,
        status=run_service.STATUS_COMPLETED,
        result={"session_id": args.session, "metrics": result.metrics},
    )
    print(json_dump(result.metrics))
    return 0


def json_dump(payload: object) -> str:
    import json

    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)


if __name__ == "__main__":
    raise SystemExit(main())
