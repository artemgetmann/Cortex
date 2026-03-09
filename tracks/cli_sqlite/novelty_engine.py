from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class NoveltyTaskSpec:
    """Static metadata for one runnable task.

    The engine stays legible by keeping this catalog explicit.
    We are not trying to "discover" difficulty or transfer value from vibes.
    """

    task_id: str
    domain: str
    family_id: str
    difficulty: float
    transfer_value: float
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class FamilySummary:
    """Aggregated view of one task family.

    This is the machine's weakness map in plain form:
    how often this family passed, how noisy it is, and whether lessons seem to help.
    """

    family_id: str
    domain: str
    bucket: str
    novelty_score: float
    runs_total: int
    task_ids: tuple[str, ...]
    task_ids_seen: tuple[str, ...]
    suggested_task_id: str
    pass_rate: float
    last5_pass_rate: float
    mean_score: float
    mean_errors: float
    mean_lesson_activations: float
    lesson_activation_rate: float
    mean_retrieval_help_ratio: float
    repeated_failure_signatures: tuple[str, ...]
    variants_seen: int
    last_attempted_at: str
    rationale: tuple[str, ...]


@dataclass(frozen=True)
class NoveltyRecommendation:
    """One scheduler recommendation.

    `mode` is intentionally simple:
    - exploitation = press on a known weak spot
    - exploration = probe transfer or an unseen family
    """

    slot: str
    mode: str
    domain: str
    family_id: str
    task_id: str
    bucket: str
    novelty_score: float
    why: tuple[str, ...]


@dataclass(frozen=True)
class NoveltySnapshot:
    """Serializable novelty engine output."""

    generated_at: str
    sessions_root: str
    families: tuple[FamilySummary, ...]
    recommendations: tuple[NoveltyRecommendation, ...]


# Keep the catalog explicit. It is easier to reason about than inference rules
# scattered across the repo, and it lets us control "family" boundaries on purpose.
_TASK_SPECS: tuple[NoveltyTaskSpec, ...] = (
    NoveltyTaskSpec("basic_transform", "gridtool", "gridtool_transform", 0.25, 0.20, ("transform", "columns")),
    NoveltyTaskSpec("aggregate_report", "gridtool", "gridtool_aggregate", 0.35, 0.35, ("aggregation", "groupby")),
    NoveltyTaskSpec(
        "aggregate_report_holdout",
        "gridtool",
        "gridtool_aggregate",
        0.45,
        0.80,
        ("aggregation", "transfer"),
    ),
    NoveltyTaskSpec("multi_step_pipeline", "gridtool", "gridtool_pipeline", 0.65, 0.45, ("pipeline", "multi_stage")),
    NoveltyTaskSpec("multi_agg_pipeline", "gridtool", "gridtool_pipeline", 0.80, 0.70, ("pipeline", "aggregation")),
    NoveltyTaskSpec("aggregate_report", "fluxtool", "fluxtool_aggregate", 0.35, 0.35, ("aggregation", "groupby")),
    NoveltyTaskSpec(
        "aggregate_report_holdout",
        "fluxtool",
        "fluxtool_aggregate",
        0.50,
        0.80,
        ("aggregation", "transfer"),
    ),
    NoveltyTaskSpec("multi_step_pipeline", "fluxtool", "fluxtool_pipeline", 0.65, 0.45, ("pipeline", "multi_stage")),
    NoveltyTaskSpec("multi_agg_pipeline", "fluxtool", "fluxtool_pipeline", 0.80, 0.70, ("pipeline", "aggregation")),
    NoveltyTaskSpec("import_aggregate", "sqlite", "sqlite_import", 0.35, 0.25, ("schema", "import")),
    NoveltyTaskSpec("idempotent_rerun", "sqlite", "sqlite_idempotent", 0.55, 0.45, ("idempotent", "upsert")),
    NoveltyTaskSpec(
        "incremental_reconcile_nano",
        "sqlite",
        "sqlite_incremental_reconcile",
        0.68,
        0.60,
        ("incremental", "dedupe"),
    ),
    NoveltyTaskSpec(
        "incremental_reconcile",
        "sqlite",
        "sqlite_incremental_reconcile",
        0.80,
        0.80,
        ("incremental", "reconcile"),
    ),
    NoveltyTaskSpec(
        "incremental_reconcile_audit_transfer",
        "sqlite",
        "sqlite_incremental_reconcile",
        0.88,
        0.95,
        ("incremental", "audit", "transfer"),
    ),
    NoveltyTaskSpec(
        "partial_failure_recovery",
        "sqlite",
        "sqlite_partial_recovery",
        0.90,
        0.85,
        ("recovery", "reconcile"),
    ),
    NoveltyTaskSpec("shell_excel_build_report", "shell", "shell_excel", 0.35, 0.30, ("files", "aggregation")),
    NoveltyTaskSpec("shell_excel_multi_summary", "shell", "shell_excel", 0.60, 0.50, ("files", "multi_stage")),
    NoveltyTaskSpec(
        "shell_excel_openpyxl_summary",
        "shell",
        "shell_excel",
        0.70,
        0.65,
        ("openpyxl", "reporting"),
    ),
    NoveltyTaskSpec(
        "shell_git_train_release_flow",
        "shell",
        "shell_git_hotfix",
        0.50,
        0.40,
        ("git", "release_flow"),
    ),
    NoveltyTaskSpec("shell_git_transfer_hotfix", "shell", "shell_git_hotfix", 0.82, 0.75, ("git", "hotfix")),
    NoveltyTaskSpec(
        "shell_git_transfer_hotfix_hard",
        "shell",
        "shell_git_hotfix",
        0.92,
        0.95,
        ("git", "conflict_resolution"),
    ),
    NoveltyTaskSpec("artic_search_basic", "artic", "artic_search", 0.25, 0.20, ("search", "query")),
    NoveltyTaskSpec(
        "artic_pagination_extract",
        "artic",
        "artic_extract",
        0.55,
        0.50,
        ("pagination", "extraction"),
    ),
    NoveltyTaskSpec("artic_followup_fetch", "artic", "artic_extract", 0.70, 0.75, ("followup", "extraction")),
)


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _round(value: float) -> float:
    return round(float(value), 3)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def default_task_specs() -> tuple[NoveltyTaskSpec, ...]:
    return _TASK_SPECS


def _metrics_rows(sessions_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for metrics_path in sorted(sessions_root.glob("session-*/metrics.json")):
        try:
            parsed = json.loads(metrics_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(parsed, dict):
            continue
        row = dict(parsed)
        # File mtime is the most reliable timestamp we have across old and new runs.
        row["_observed_at"] = datetime.fromtimestamp(metrics_path.stat().st_mtime, tz=timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
        rows.append(row)
    return rows


def _family_specs(task_specs: tuple[NoveltyTaskSpec, ...]) -> dict[tuple[str, str], list[NoveltyTaskSpec]]:
    grouped: dict[tuple[str, str], list[NoveltyTaskSpec]] = {}
    for spec in task_specs:
        grouped.setdefault((spec.domain, spec.family_id), []).append(spec)
    for specs in grouped.values():
        specs.sort(key=lambda item: (item.difficulty, item.task_id))
    return grouped


def _select_unseen_or_hardest_task(*, specs: list[NoveltyTaskSpec], seen_task_ids: set[str]) -> str:
    unseen = [spec for spec in specs if spec.task_id not in seen_task_ids]
    if unseen:
        unseen.sort(key=lambda item: (-item.transfer_value, -item.difficulty, item.task_id))
        return unseen[0].task_id
    ranked = sorted(specs, key=lambda item: (-item.transfer_value, -item.difficulty, item.task_id))
    return ranked[0].task_id


def _select_retry_task(*, specs: list[NoveltyTaskSpec], recent_failed_task_id: str) -> str:
    if recent_failed_task_id:
        for spec in specs:
            if spec.task_id == recent_failed_task_id:
                return recent_failed_task_id
    ranked = sorted(specs, key=lambda item: (-item.difficulty, -item.transfer_value, item.task_id))
    return ranked[0].task_id


def _bucket_for_family(
    *,
    runs_total: int,
    pass_rate: float,
    last5_pass_rate: float,
    mean_errors: float,
    lesson_activation_rate: float,
    total_task_ids: int,
    seen_task_ids: set[str],
) -> str:
    # New family means we have zero direct evidence. That is exploration territory by definition.
    if runs_total == 0:
        return "new_family"

    # If we know the family but have not touched sibling tasks, use it as a transfer probe.
    # This check comes before "saturated" on purpose: the base task may be mastered
    # while the family still has unseen siblings worth probing.
    if len(seen_task_ids) < total_task_ids and pass_rate >= 0.55:
        return "transfer_probe"

    # Saturated means the whole family slice is too easy to teach us much right now.
    if runs_total >= 3 and pass_rate >= 0.90 and last5_pass_rate >= 0.90 and mean_errors <= 1.0:
        return "saturated"

    # Weak spots are where passes are low, recent passes are low, or the family still throws errors.
    if pass_rate < 0.75 or last5_pass_rate < 0.60 or mean_errors >= 2.0:
        return "known_weak"

    # If lessons never activate and the task already passes, it is not a useful teacher.
    if pass_rate >= 0.80 and lesson_activation_rate <= 0.05:
        return "bad_instrument"

    return "transfer_probe"


def _recency_bonus(last_attempted_at: str) -> float:
    if not last_attempted_at:
        return 0.75
    try:
        observed = datetime.fromisoformat(last_attempted_at.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    age_days = max(0.0, (datetime.now(tz=timezone.utc) - observed).total_seconds() / 86400.0)
    return _clamp(age_days / 14.0)


def _novelty_score(
    *,
    pass_rate: float,
    runs_total: int,
    mean_errors: float,
    retrieval_help_ratio: float,
    transfer_value: float,
    last_attempted_at: str,
    bucket: str,
    mean_difficulty: float,
) -> tuple[float, list[str]]:
    # Keep the formula simple and inspectable.
    weakness = _clamp((1.0 - pass_rate) + min(mean_errors / 6.0, 0.5))
    uncertainty = 1.0 if runs_total == 0 else _clamp((4.0 - float(runs_total)) / 4.0)
    transfer = _clamp(transfer_value)
    recency = _recency_bonus(last_attempted_at)
    saturation_penalty = 0.9 if bucket == "saturated" else 0.0
    bad_instrument_penalty = 0.7 if bucket == "bad_instrument" else 0.0
    # If retrieval already helps a lot, keep some pressure on this family because it is paying rent.
    retrieval_bonus = _clamp(retrieval_help_ratio) * 0.25
    cost_penalty = _clamp(mean_difficulty) * 0.20

    score = weakness + uncertainty + transfer + recency + retrieval_bonus - saturation_penalty - bad_instrument_penalty - cost_penalty
    rationale = [
        f"weakness={_round(weakness)}",
        f"uncertainty={_round(uncertainty)}",
        f"transfer={_round(transfer)}",
        f"recency={_round(recency)}",
    ]
    if retrieval_bonus > 0.0:
        rationale.append(f"retrieval_bonus={_round(retrieval_bonus)}")
    if saturation_penalty > 0.0:
        rationale.append(f"saturation_penalty={_round(saturation_penalty)}")
    if bad_instrument_penalty > 0.0:
        rationale.append(f"bad_instrument_penalty={_round(bad_instrument_penalty)}")
    return _round(score), rationale


def build_snapshot(*, sessions_root: Path, task_specs: tuple[NoveltyTaskSpec, ...] | None = None) -> NoveltySnapshot:
    specs = task_specs or default_task_specs()
    grouped_specs = _family_specs(specs)
    metric_rows = _metrics_rows(sessions_root)

    grouped_rows: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in metric_rows:
        task_id = str(row.get("task_id", "")).strip()
        domain = str(row.get("domain", "")).strip()
        spec = next((item for item in specs if item.task_id == task_id and item.domain == domain), None)
        if spec is None:
            continue
        grouped_rows.setdefault((domain, spec.family_id), []).append(row)

    families: list[FamilySummary] = []
    for key in sorted(grouped_specs):
        domain, family_id = key
        family_specs = grouped_specs[key]
        rows = grouped_rows.get(key, [])
        rows.sort(key=lambda item: str(item.get("_observed_at", "")))
        seen_task_ids = {str(item.get("task_id", "")).strip() for item in rows if str(item.get("task_id", "")).strip()}
        pass_values = [1.0 if bool(item.get("eval_passed", False)) else 0.0 for item in rows]
        error_values = [_safe_int(item.get("error_count", 0), default=0) for item in rows]
        score_values = [_safe_float(item.get("eval_score", 0.0), default=0.0) for item in rows]
        activation_values = [_safe_int(item.get("lesson_activations", 0), default=0) for item in rows]
        retrieval_values = [_safe_float(item.get("retrieval_help_ratio", 0.0), default=0.0) for item in rows]

        repeated_signatures: Counter[str] = Counter()
        recent_failed_task_id = ""
        for row in rows:
            if not bool(row.get("eval_passed", False)):
                recent_failed_task_id = str(row.get("task_id", "")).strip() or recent_failed_task_id
            raw_signatures = row.get("repeated_error_signatures", [])
            if isinstance(raw_signatures, list):
                for signature in raw_signatures:
                    text = str(signature).strip()
                    if text:
                        repeated_signatures[text] += 1

        runs_total = len(rows)
        pass_rate = sum(pass_values) / float(runs_total) if runs_total else 0.0
        last5 = pass_values[-5:]
        last5_pass_rate = sum(last5) / float(len(last5)) if last5 else 0.0
        mean_score = sum(score_values) / float(len(score_values)) if score_values else 0.0
        mean_errors = sum(error_values) / float(len(error_values)) if error_values else 0.0
        mean_activations = sum(activation_values) / float(len(activation_values)) if activation_values else 0.0
        activation_rate = sum(1 for value in activation_values if value > 0) / float(len(activation_values)) if activation_values else 0.0
        retrieval_help_ratio = sum(retrieval_values) / float(len(retrieval_values)) if retrieval_values else 0.0
        last_attempted_at = str(rows[-1].get("_observed_at", "")) if rows else ""
        mean_difficulty = sum(spec.difficulty for spec in family_specs) / float(len(family_specs))
        transfer_value = max(spec.transfer_value for spec in family_specs)

        bucket = _bucket_for_family(
            runs_total=runs_total,
            pass_rate=pass_rate,
            last5_pass_rate=last5_pass_rate,
            mean_errors=mean_errors,
            lesson_activation_rate=activation_rate,
            total_task_ids=len(family_specs),
            seen_task_ids=seen_task_ids,
        )
        novelty_score, rationale = _novelty_score(
            pass_rate=pass_rate,
            runs_total=runs_total,
            mean_errors=mean_errors,
            retrieval_help_ratio=retrieval_help_ratio,
            transfer_value=transfer_value,
            last_attempted_at=last_attempted_at,
            bucket=bucket,
            mean_difficulty=mean_difficulty,
        )
        if bucket == "known_weak":
            suggested_task_id = _select_retry_task(specs=family_specs, recent_failed_task_id=recent_failed_task_id)
        else:
            suggested_task_id = _select_unseen_or_hardest_task(specs=family_specs, seen_task_ids=seen_task_ids)

        families.append(
            FamilySummary(
                family_id=family_id,
                domain=domain,
                bucket=bucket,
                novelty_score=novelty_score,
                runs_total=runs_total,
                task_ids=tuple(spec.task_id for spec in family_specs),
                task_ids_seen=tuple(sorted(seen_task_ids)),
                suggested_task_id=suggested_task_id,
                pass_rate=_round(pass_rate),
                last5_pass_rate=_round(last5_pass_rate),
                mean_score=_round(mean_score),
                mean_errors=_round(mean_errors),
                mean_lesson_activations=_round(mean_activations),
                lesson_activation_rate=_round(activation_rate),
                mean_retrieval_help_ratio=_round(retrieval_help_ratio),
                repeated_failure_signatures=tuple(signature for signature, _ in repeated_signatures.most_common(3)),
                variants_seen=len(seen_task_ids),
                last_attempted_at=last_attempted_at,
                rationale=tuple(rationale),
            )
        )

    recommendations = tuple(select_recommendations(families=tuple(families)))
    return NoveltySnapshot(
        generated_at=_utc_now(),
        sessions_root=str(sessions_root),
        families=tuple(sorted(families, key=lambda item: (-item.novelty_score, item.family_id))),
        recommendations=recommendations,
    )


def select_recommendations(*, families: tuple[FamilySummary, ...], limit: int = 3) -> list[NoveltyRecommendation]:
    ordered = sorted(families, key=lambda item: (-item.novelty_score, item.family_id))
    by_bucket: dict[str, list[FamilySummary]] = {}
    for family in ordered:
        by_bucket.setdefault(family.bucket, []).append(family)

    chosen_family_ids: set[str] = set()
    recommendations: list[NoveltyRecommendation] = []

    def _take(bucket: str, *, slot: str, mode: str) -> None:
        for family in by_bucket.get(bucket, []):
            if family.family_id in chosen_family_ids:
                continue
            chosen_family_ids.add(family.family_id)
            recommendations.append(
                NoveltyRecommendation(
                    slot=slot,
                    mode=mode,
                    domain=family.domain,
                    family_id=family.family_id,
                    task_id=family.suggested_task_id,
                    bucket=family.bucket,
                    novelty_score=family.novelty_score,
                    why=family.rationale,
                )
            )
            return

    # One weak spot, one transfer probe, one new family is the smallest useful mix.
    _take("known_weak", slot="known_weak", mode="exploitation")
    _take("transfer_probe", slot="transfer_probe", mode="exploration")
    _take("new_family", slot="new_family", mode="exploration")

    # If a bucket is missing, fill from the next best unsaturated families.
    for family in ordered:
        if len(recommendations) >= max(1, int(limit)):
            break
        if family.family_id in chosen_family_ids:
            continue
        if family.bucket == "saturated":
            continue
        chosen_family_ids.add(family.family_id)
        recommendations.append(
            NoveltyRecommendation(
                slot="fallback",
                mode="exploration" if family.bucket in {"new_family", "transfer_probe"} else "exploitation",
                domain=family.domain,
                family_id=family.family_id,
                task_id=family.suggested_task_id,
                bucket=family.bucket,
                novelty_score=family.novelty_score,
                why=family.rationale,
            )
        )

    return recommendations[: max(1, int(limit))]


def snapshot_to_dict(snapshot: NoveltySnapshot) -> dict[str, Any]:
    return {
        "generated_at": snapshot.generated_at,
        "sessions_root": snapshot.sessions_root,
        "families": [asdict(item) for item in snapshot.families],
        "recommendations": [asdict(item) for item in snapshot.recommendations],
    }


def render_snapshot_text(snapshot: NoveltySnapshot) -> str:
    lines = [
        "Novelty Engine Snapshot",
        f"- generated_at: {snapshot.generated_at}",
        f"- sessions_root: {snapshot.sessions_root}",
        "",
        "Recommendations",
    ]
    for item in snapshot.recommendations:
        lines.append(
            f"- [{item.slot}] {item.task_id} ({item.domain}) mode={item.mode} bucket={item.bucket} score={item.novelty_score}"
        )
        for reason in item.why:
            lines.append(f"  - {reason}")

    lines.append("")
    lines.append("Family Summary")
    for family in snapshot.families:
        lines.append(
            f"- {family.family_id}: bucket={family.bucket} task={family.suggested_task_id} runs={family.runs_total} "
            f"pass={family.pass_rate} last5={family.last5_pass_rate} errors={family.mean_errors} score={family.novelty_score}"
        )
    return "\n".join(lines)
