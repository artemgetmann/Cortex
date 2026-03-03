from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _tier_from_model(model_name: str) -> str:
    lowered = model_name.lower()
    if "opus" in lowered:
        return "opus"
    if "sonnet" in lowered:
        return "sonnet"
    return "haiku"


def _model_from_tier(tier: str, *, base_model: str, sonnet_model: str, opus_model: str) -> str:
    if tier == "haiku":
        return base_model
    if tier == "sonnet":
        return sonnet_model
    return opus_model


def _load_escalation_state(*, learning_root: Path, escalation_state_path: Path, base_model: str) -> dict[str, Any]:
    learning_root.mkdir(parents=True, exist_ok=True)
    default = {
        "tier": _tier_from_model(base_model),
        "override_runs_remaining": 0,
        "low_score_streak": 0,
        "critic_no_updates_streak": 0,
        "last_trigger": None,
    }
    if not escalation_state_path.exists():
        return default
    try:
        parsed = json.loads(escalation_state_path.read_text(encoding="utf-8"))
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


def _save_escalation_state(*, learning_root: Path, escalation_state_path: Path, state: dict[str, Any]) -> None:
    learning_root.mkdir(parents=True, exist_ok=True)
    escalation_state_path.write_text(json.dumps(state, indent=2, ensure_ascii=True), encoding="utf-8")


def _resolve_critic_model_for_run(
    *,
    base_model: str,
    auto_escalate: bool,
    state: dict[str, Any],
    sonnet_model: str,
    opus_model: str,
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
    return _model_from_tier(tier, base_model=base_model, sonnet_model=sonnet_model, opus_model=opus_model), state


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


def _required_skill_refs_for_domain(
    *,
    routed_refs: list[str],
    domain: str,
    require_skill_read: bool,
    task_id: str,
) -> set[str]:
    """Gate only on active-domain skills to prevent cross-domain deadlocks."""
    if not require_skill_read:
        return set()
    domain_prefix = f"{domain}/"
    domain_refs = [ref for ref in routed_refs if ref.startswith(domain_prefix)]
    if not domain_refs:
        return set()

    normalized_task = str(task_id).strip().lower().replace("_", "-")
    if normalized_task:
        for ref in domain_refs:
            if normalized_task in ref.lower():
                return {ref}
    return {domain_refs[0]}


def _build_critic_context_query(
    *,
    task_text: str,
    eval_result: dict[str, Any],
    events_tail: list[dict[str, Any]],
) -> str:
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
    # Keep source identifiers so observability can tie critic decisions to docs.
    if not chunks:
        return ""
    lines: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        title = getattr(chunk, "source_title", "doc")
        source_id = getattr(chunk, "source_id", f"doc-{idx}")
        text = getattr(chunk, "text", "")
        lines.append(f"[{idx}] {title} ({source_id})\n{text}")
    return "\n\n".join(lines)


def _resolve_transfer_retrieval_policy(
    *,
    enable_transfer_retrieval: bool,
    transfer_retrieval_max_results: int,
    transfer_retrieval_score_weight: float,
    transfer_policy_always: str,
    transfer_policy_off: str,
    transfer_policy_auto: str,
) -> str:
    if bool(enable_transfer_retrieval):
        return transfer_policy_always
    if int(transfer_retrieval_max_results) <= 0 or float(transfer_retrieval_score_weight) <= 0.0:
        return transfer_policy_off
    return transfer_policy_auto
