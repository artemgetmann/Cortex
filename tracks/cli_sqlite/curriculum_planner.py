"""Curriculum planning helpers for CLI learning-curve experiments.

This module keeps selection logic deterministic and lightweight so it can be
used both in scripts and in unit tests without extra runtime dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CURRICULUM_MODES: tuple[str, ...] = ("fixed", "auto")
DEFAULT_CURRICULUM_MODE = "fixed"


@dataclass(frozen=True)
class CurriculumTask:
    """Candidate task metadata used by the adaptive planner."""

    task_id: str
    domain: str
    difficulty: float
    gap_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class CurriculumDecision:
    """Planner output for one run."""

    task_id: str
    domain: str
    planner_score: float
    rationale: str


@dataclass(frozen=True)
class CurriculumOutcome:
    """Minimal run feedback needed to adapt future selections."""

    run_index: int
    task_id: str
    domain: str
    score: float
    passed: bool
    steps: int
    tool_errors: int
    repeated_error_signatures: tuple[str, ...] = ()


_DOMAIN_TASKS: dict[str, tuple[CurriculumTask, ...]] = {
    "gridtool": (
        CurriculumTask("basic_transform", "gridtool", 0.25, ("transform", "columns")),
        CurriculumTask("aggregate_report", "gridtool", 0.35, ("aggregation", "groupby")),
        CurriculumTask("aggregate_report_holdout", "gridtool", 0.45, ("aggregation", "transfer")),
        CurriculumTask("multi_step_pipeline", "gridtool", 0.65, ("pipeline", "multi_stage")),
        CurriculumTask("multi_agg_pipeline", "gridtool", 0.80, ("pipeline", "aggregation")),
    ),
    "fluxtool": (
        CurriculumTask("aggregate_report", "fluxtool", 0.35, ("aggregation", "groupby")),
        CurriculumTask("aggregate_report_holdout", "fluxtool", 0.50, ("aggregation", "transfer")),
        CurriculumTask("multi_step_pipeline", "fluxtool", 0.65, ("pipeline", "multi_stage")),
        CurriculumTask("multi_agg_pipeline", "fluxtool", 0.80, ("pipeline", "aggregation")),
    ),
    "sqlite": (
        CurriculumTask("import_aggregate", "sqlite", 0.35, ("schema", "import")),
        CurriculumTask("idempotent_rerun", "sqlite", 0.55, ("idempotent", "upsert")),
        # Nano-friendly bridge task: keeps reconcile shape but relaxes closure surface.
        CurriculumTask("incremental_reconcile_nano", "sqlite", 0.68, ("incremental", "dedupe")),
        CurriculumTask("incremental_reconcile", "sqlite", 0.80, ("incremental", "reconcile")),
        CurriculumTask("partial_failure_recovery", "sqlite", 0.90, ("recovery", "reconcile")),
    ),
    "shell": (
        CurriculumTask("shell_excel_build_report", "shell", 0.35, ("files", "aggregation")),
        CurriculumTask("shell_git_train_release_flow", "shell", 0.50, ("git", "release_flow")),
        CurriculumTask("shell_excel_multi_summary", "shell", 0.60, ("files", "multi_stage")),
        CurriculumTask("shell_excel_openpyxl_summary", "shell", 0.70, ("openpyxl", "reporting")),
        CurriculumTask("shell_git_transfer_hotfix", "shell", 0.82, ("git", "hotfix")),
        CurriculumTask("shell_git_transfer_hotfix_hard", "shell", 0.92, ("git", "conflict_resolution")),
    ),
    "artic": (
        CurriculumTask("artic_search_basic", "artic", 0.25, ("search", "query")),
        CurriculumTask("artic_pagination_extract", "artic", 0.55, ("pagination", "extraction")),
        CurriculumTask("artic_followup_fetch", "artic", 0.70, ("followup", "extraction")),
    ),
}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_curriculum_tasks(*, domain: str, seed_task_id: str) -> tuple[CurriculumTask, ...]:
    """Build deterministic task candidates for the requested domain.

    The caller-provided task is always kept in the pool as an anchor to avoid
    hard failures when a benchmark uses custom task IDs.
    """
    normalized_domain = str(domain).strip().lower()
    seed = str(seed_task_id).strip()
    rows = list(_DOMAIN_TASKS.get(normalized_domain, ()))
    if seed and all(task.task_id != seed for task in rows):
        rows.insert(0, CurriculumTask(seed, normalized_domain, 0.50, ("anchor_task",)))
    if not rows:
        rows.append(CurriculumTask(seed or "aggregate_report", normalized_domain, 0.50, ("anchor_task",)))
    return tuple(rows)


def outcome_from_metrics(
    *,
    run_index: int,
    task_id: str,
    domain: str,
    metrics: dict[str, Any],
) -> CurriculumOutcome:
    signatures_raw = metrics.get("repeated_error_signatures", [])
    signatures: list[str] = []
    if isinstance(signatures_raw, list):
        for value in signatures_raw:
            item = str(value).strip()
            if item:
                signatures.append(item)
    return CurriculumOutcome(
        run_index=max(1, int(run_index)),
        task_id=str(task_id),
        domain=str(domain),
        score=_as_float(metrics.get("eval_score", 0.0), default=0.0),
        passed=bool(metrics.get("eval_passed", False)),
        steps=max(0, _as_int(metrics.get("steps", 0), default=0)),
        tool_errors=max(0, _as_int(metrics.get("tool_errors", 0), default=0)),
        repeated_error_signatures=tuple(signatures),
    )


class FixedCurriculumPlanner:
    """Planner that always returns the requested task/domain pair."""

    def __init__(self, *, task_id: str, domain: str) -> None:
        self._task_id = str(task_id)
        self._domain = str(domain)

    def propose_next(self, *, run_index: int) -> CurriculumDecision:
        return CurriculumDecision(
            task_id=self._task_id,
            domain=self._domain,
            planner_score=0.0,
            rationale=f"fixed schedule for run {int(run_index)}",
        )

    def record_outcome(self, outcome: CurriculumOutcome) -> None:  # noqa: ARG002
        return None


class AdaptiveCurriculumPlanner:
    """Planner that prioritizes unresolved failures and right-sized difficulty."""

    def __init__(
        self,
        *,
        seed_task_id: str,
        domain: str,
        candidates: tuple[CurriculumTask, ...],
    ) -> None:
        self._seed_task_id = str(seed_task_id)
        self._domain = str(domain)
        self._candidates = tuple(candidates)
        self._history: list[CurriculumOutcome] = []
        self._difficulty_by_task = {task.task_id: float(task.difficulty) for task in self._candidates}

    def record_outcome(self, outcome: CurriculumOutcome) -> None:
        self._history.append(outcome)

    def propose_next(self, *, run_index: int) -> CurriculumDecision:
        if not self._history:
            return CurriculumDecision(
                task_id=self._seed_task_id,
                domain=self._domain,
                planner_score=0.0,
                rationale="warm start on seed task before adaptive routing",
            )

        unresolved_signatures = self._collect_unresolved_signatures()
        target_difficulty = self._target_difficulty()
        seen_counts = self._seen_counts()
        recent_task = self._history[-1].task_id if self._history else ""

        best_score = float("-inf")
        best_task = self._candidates[0]
        best_rationale = ""

        for task in self._candidates:
            task_score = self._score_task(
                task=task,
                target_difficulty=target_difficulty,
                unresolved_signatures=unresolved_signatures,
                seen_count=seen_counts.get(task.task_id, 0),
                last_task_id=recent_task,
            )
            if task_score > best_score or (task_score == best_score and task.task_id < best_task.task_id):
                best_score = task_score
                best_task = task
                best_rationale = self._build_rationale(
                    task=task,
                    score=task_score,
                    target_difficulty=target_difficulty,
                    unresolved_signatures=unresolved_signatures,
                )

        return CurriculumDecision(
            task_id=best_task.task_id,
            domain=best_task.domain,
            planner_score=best_score,
            rationale=best_rationale,
        )

    def _seen_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for outcome in self._history:
            counts[outcome.task_id] = counts.get(outcome.task_id, 0) + 1
        return counts

    def _target_difficulty(self) -> float:
        recent = self._history[-3:]
        if not recent:
            return self._difficulty_by_task.get(self._seed_task_id, 0.50)

        pass_rate = sum(1 for item in recent if item.passed) / float(len(recent))
        avg_seen_difficulty = sum(
            self._difficulty_by_task.get(item.task_id, 0.50) for item in recent
        ) / float(len(recent))

        if pass_rate <= 0.34:
            return max(0.10, avg_seen_difficulty - 0.20)
        if pass_rate >= 0.80:
            return min(0.95, avg_seen_difficulty + 0.15)
        return avg_seen_difficulty

    def _collect_unresolved_signatures(self) -> set[str]:
        failed: dict[str, int] = {}
        resolved: dict[str, int] = {}
        latest_pass_by_task: dict[str, int] = {}
        for outcome in self._history:
            if outcome.passed:
                latest_pass_by_task[outcome.task_id] = max(
                    latest_pass_by_task.get(outcome.task_id, 0),
                    int(outcome.run_index),
                )
        for outcome in self._history:
            # A successful rerun on the same task is treated as resolution for
            # earlier signatures from that task; this keeps the planner from
            # getting stuck retrying already-fixed failures.
            if (
                not outcome.passed
                and latest_pass_by_task.get(outcome.task_id, 0) > int(outcome.run_index)
            ):
                continue
            signatures = list(outcome.repeated_error_signatures)
            if outcome.tool_errors > 0:
                signatures.append("tool_errors")
            if outcome.score < 0.75:
                signatures.append("low_score")
            if not signatures:
                signatures.append(f"task:{outcome.task_id}")
            bucket = resolved if outcome.passed else failed
            for signature in signatures:
                bucket[signature] = bucket.get(signature, 0) + 1
        return {
            signature
            for signature, failures in failed.items()
            if failures > resolved.get(signature, 0)
        }

    def _score_task(
        self,
        *,
        task: CurriculumTask,
        target_difficulty: float,
        unresolved_signatures: set[str],
        seen_count: int,
        last_task_id: str,
    ) -> float:
        tags = set(task.gap_tags)
        gap_overlap = len(tags.intersection(unresolved_signatures))
        failed_same_task = any(
            (not item.passed) and item.task_id == task.task_id for item in self._history[-3:]
        )
        successful_recently = sum(
            1 for item in self._history[-3:] if item.passed and item.task_id == task.task_id
        )

        # Scoring rationale:
        # - Gap overlap has the highest weight so we re-target unresolved failure
        #   signatures instead of spending runs on already-solved areas.
        # - Difficulty fit is the second strongest term; it keeps tasks in the
        #   "challenge but solvable" zone based on the recent pass rate.
        # - Novelty/repeat penalties are smaller tie-breakers to avoid mode lock.
        score = 0.0
        score += 3.0 * float(gap_overlap)
        score += max(0.0, 1.5 - (abs(float(task.difficulty) - target_difficulty) * 3.0))
        if failed_same_task:
            score += 1.0
        if successful_recently >= 2 and gap_overlap == 0:
            score -= 1.2
        if seen_count == 0:
            score += 0.4
        if last_task_id and last_task_id == task.task_id:
            score -= 0.6
        return score

    def _build_rationale(
        self,
        *,
        task: CurriculumTask,
        score: float,
        target_difficulty: float,
        unresolved_signatures: set[str],
    ) -> str:
        overlap = sorted(set(task.gap_tags).intersection(unresolved_signatures))
        overlap_text = ",".join(overlap) if overlap else "none"
        return (
            f"auto score={score:.2f}; target_difficulty={target_difficulty:.2f}; "
            f"gap_overlap={overlap_text}"
        )


def create_curriculum_planner(
    *,
    mode: str,
    task_id: str,
    domain: str,
) -> FixedCurriculumPlanner | AdaptiveCurriculumPlanner:
    normalized_mode = str(mode).strip().lower() or DEFAULT_CURRICULUM_MODE
    if normalized_mode == "auto":
        return AdaptiveCurriculumPlanner(
            seed_task_id=task_id,
            domain=domain,
            candidates=build_curriculum_tasks(domain=domain, seed_task_id=task_id),
        )
    return FixedCurriculumPlanner(task_id=task_id, domain=domain)
