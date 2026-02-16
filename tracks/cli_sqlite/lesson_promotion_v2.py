from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from tracks.cli_sqlite.lesson_store_v2 import LessonRecord, load_lesson_records, write_lesson_records


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _mean(values: Sequence[float]) -> float:
    return (sum(values) / float(len(values))) if values else 0.0


@dataclass(frozen=True)
class LessonOutcome:
    lesson_id: str
    error_reduction: float
    step_efficiency_gain: float
    referee_score_gain: float | None = None
    major_regression: bool = False
    contradiction_lost: bool = False


def compute_utility(
    *,
    error_reduction: float,
    step_efficiency_gain: float,
    referee_score_gain: float | None = None,
) -> float:
    """Compute utility using the exact weighting in the V2 plan."""
    if referee_score_gain is None:
        return (0.65 * float(error_reduction)) + (0.35 * float(step_efficiency_gain))
    return (
        (0.50 * float(error_reduction))
        + (0.30 * float(step_efficiency_gain))
        + (0.20 * float(referee_score_gain))
    )


def _update_record(record: LessonRecord, outcome: LessonOutcome) -> LessonRecord:
    utility = compute_utility(
        error_reduction=outcome.error_reduction,
        step_efficiency_gain=outcome.step_efficiency_gain,
        referee_score_gain=outcome.referee_score_gain,
    )
    history = tuple(list(record.utility_history[-29:]) + [utility])
    helpful = record.helpful_count + (1 if utility > 0 else 0)
    harmful = record.harmful_count + (1 if utility <= 0 else 0)
    major_regressions = record.major_regressions + (1 if outcome.major_regression else 0)
    contradiction_losses = record.contradiction_losses + (1 if outcome.contradiction_lost else 0)
    retrieval_count = record.retrieval_count + 1

    # Reliability tracks smoothed utility impact and stays in [0,1].
    utility_mapped = _clamp((utility + 1.0) / 2.0, 0.0, 1.0)
    reliability = _clamp((0.7 * record.reliability) + (0.3 * utility_mapped), 0.0, 1.0)

    status = record.status
    relevant_runs = len(history)
    mean_utility = _mean(history[-min(10, relevant_runs):])

    # Suppression guards run first: harmful retrievals or contradiction losses
    # should immediately stop future retrieval amplification.
    if contradiction_losses > 0:
        status = "suppressed"
    elif retrieval_count >= 3 and mean_utility <= 0.0:
        status = "suppressed"
    elif (
        status == "candidate"
        and relevant_runs >= 3
        and mean_utility >= 0.20
        and major_regressions == 0
    ):
        status = "promoted"

    return LessonRecord(
        **{
            **record.__dict__,
            "status": status,
            "reliability": reliability,
            "retrieval_count": retrieval_count,
            "helpful_count": helpful,
            "harmful_count": harmful,
            "utility_history": history,
            "major_regressions": major_regressions,
            "contradiction_losses": contradiction_losses,
        }
    )


def apply_outcomes(
    *,
    path: Path,
    outcomes: Sequence[LessonOutcome],
) -> dict[str, int]:
    if not outcomes:
        return {"updated": 0, "promoted": 0, "suppressed": 0}
    records = load_lesson_records(path)
    if not records:
        return {"updated": 0, "promoted": 0, "suppressed": 0}

    by_id = {record.lesson_id: record for record in records}
    promoted = 0
    suppressed = 0
    updated = 0

    for outcome in outcomes:
        current = by_id.get(outcome.lesson_id)
        if current is None:
            continue
        before = current.status
        after = _update_record(current, outcome)
        by_id[outcome.lesson_id] = after
        updated += 1
        if before != "promoted" and after.status == "promoted":
            promoted += 1
        if before != "suppressed" and after.status == "suppressed":
            suppressed += 1

    write_lesson_records(path, list(by_id.values()))
    return {"updated": updated, "promoted": promoted, "suppressed": suppressed}


__all__ = ["LessonOutcome", "apply_outcomes", "compute_utility"]
