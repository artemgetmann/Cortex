from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


LESSON_STATUSES = ("candidate", "promoted", "suppressed", "archived")
V2_SCHEMA = "lesson_store_v2"
V2_VERSION = 1

_TEXT_WS_RE = re.compile(r"\s+")
_TEXT_TOKEN_RE = re.compile(r"[^a-z0-9\s]+")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(text: str) -> str:
    lowered = _TEXT_TOKEN_RE.sub(" ", str(text).lower())
    return _TEXT_WS_RE.sub(" ", lowered).strip()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def normalize_rule_text(rule_text: str) -> str:
    """Normalize lesson text for dedup/fingerprint identity checks."""
    return _normalize_text(rule_text)


def _stable_lesson_id(*, normalized_rule: str, trigger_fingerprints: Sequence[str]) -> str:
    """Generate a stable ID from semantic identity, not run-local metadata."""
    key = f"{normalized_rule}|{','.join(sorted(set(trigger_fingerprints)))}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return f"lsn_{digest[:20]}"


def _extract_tags_from_text(text: str) -> tuple[str, ...]:
    lower = str(text).lower()
    tags: set[str] = set()
    if any(token in lower for token in ("syntax", "parse", "expected", "unknown command", "invalid")):
        tags.add("syntax_structure")
    if any(token in lower for token in ("missing", "not found", "unknown", "undefined")):
        tags.add("unknown_symbol")
    if any(token in lower for token in ("quote", "quoted", "\"", "'")):
        tags.add("path_quote")
    if any(token in lower for token in ("operator", "eq", "neq", "gt", "lt", "gte", "lte")):
        tags.add("operator_mismatch")
    if any(token in lower for token in ("arity", "arguments", "expects", "wrong number")):
        tags.add("arity_mismatch")
    if any(token in lower for token in ("column", "field", "alias")):
        tags.add("column_reference")
    if any(token in lower for token in ("lowercase", "uppercase", "case-sensitive")):
        tags.add("function_case")
    if any(token in lower for token in ("asc", "desc", "sort", "rank")):
        tags.add("sort_direction")
    if any(token in lower for token in ("no progress", "stuck", "stall")):
        tags.add("no_progress")
    if any(token in lower for token in ("constraint", "invariant", "violation")):
        tags.add("constraint_failed")
    if any(token in lower for token in ("unsafe", "forbidden", "blocked")):
        tags.add("unsafe_action")
    if any(token in lower for token in ("distance increase", "farther", "regression")):
        tags.add("goal_distance_increase")
    if not tags:
        tags.add("generic")
    return tuple(sorted(tags))


@dataclass(frozen=True)
class LessonRecord:
    lesson_id: str
    status: str
    rule_text: str
    normalized_rule: str
    trigger_fingerprints: tuple[str, ...]
    tags: tuple[str, ...]
    task_id: str
    task: str
    domain: str
    source_session_ids: tuple[int, ...]
    reliability: float
    retrieval_count: int
    helpful_count: int
    harmful_count: int
    utility_history: tuple[float, ...]
    major_regressions: int
    contradiction_losses: int
    conflict_lesson_ids: tuple[str, ...]
    archived_reason: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_candidate(
        cls,
        *,
        session_id: int,
        task_id: str,
        task: str,
        domain: str,
        rule_text: str,
        trigger_fingerprints: Sequence[str],
        tags: Sequence[str] | None = None,
        status: str = "candidate",
    ) -> "LessonRecord":
        normalized = normalize_rule_text(rule_text)
        fingerprints = tuple(sorted({str(fp).strip() for fp in trigger_fingerprints if str(fp).strip()}))
        lesson_tags = tuple(sorted({str(tag).strip() for tag in (tags or ()) if str(tag).strip()}))
        if not lesson_tags:
            lesson_tags = _extract_tags_from_text(rule_text)
        if status not in LESSON_STATUSES:
            raise ValueError(f"Unknown lesson status: {status!r}")
        lesson_id = _stable_lesson_id(normalized_rule=normalized, trigger_fingerprints=fingerprints)
        now = _utc_now_iso()
        return cls(
            lesson_id=lesson_id,
            status=status,
            rule_text=" ".join(str(rule_text).split())[:420],
            normalized_rule=normalized,
            trigger_fingerprints=fingerprints,
            tags=lesson_tags,
            task_id=str(task_id).strip(),
            task=str(task).strip(),
            domain=str(domain).strip(),
            source_session_ids=(int(session_id),) if int(session_id) > 0 else (),
            reliability=0.5,
            retrieval_count=0,
            helpful_count=0,
            harmful_count=0,
            utility_history=(),
            major_regressions=0,
            contradiction_losses=0,
            conflict_lesson_ids=(),
            archived_reason=None,
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "LessonRecord | None":
        """Parse either v2 rows or legacy `lessons.jsonl` rows."""
        if not isinstance(row, dict):
            return None

        # Native V2 row.
        if str(row.get("memory_schema", "")) == V2_SCHEMA:
            status = str(row.get("status", "candidate")).strip().lower()
            if status not in LESSON_STATUSES:
                status = "candidate"
            normalized_rule = normalize_rule_text(str(row.get("normalized_rule", row.get("rule_text", ""))))
            rule_text = " ".join(str(row.get("rule_text", row.get("lesson", ""))).split())
            fingerprints = tuple(sorted({str(v).strip() for v in row.get("trigger_fingerprints", []) if str(v).strip()}))
            tags = tuple(sorted({str(v).strip() for v in row.get("tags", []) if str(v).strip()}))
            source_ids = tuple(
                sorted(
                    {
                        int(v)
                        for v in row.get("source_session_ids", [])
                        if isinstance(v, int) and int(v) > 0
                    }
                )
            )
            utility_history = tuple(float(v) for v in row.get("utility_history", []) if isinstance(v, (int, float)))
            lesson_id = str(row.get("lesson_id", "")).strip()
            if not lesson_id:
                lesson_id = _stable_lesson_id(normalized_rule=normalized_rule, trigger_fingerprints=fingerprints)
            return cls(
                lesson_id=lesson_id,
                status=status,
                rule_text=rule_text[:420],
                normalized_rule=normalized_rule,
                trigger_fingerprints=fingerprints,
                tags=tags or _extract_tags_from_text(rule_text),
                task_id=str(row.get("task_id", "")).strip(),
                task=str(row.get("task", "")).strip(),
                domain=str(row.get("domain", "")).strip(),
                source_session_ids=source_ids,
                reliability=_clamp(float(row.get("reliability", 0.5) or 0.5), 0.0, 1.0),
                retrieval_count=max(0, int(row.get("retrieval_count", 0) or 0)),
                helpful_count=max(0, int(row.get("helpful_count", 0) or 0)),
                harmful_count=max(0, int(row.get("harmful_count", 0) or 0)),
                utility_history=utility_history,
                major_regressions=max(0, int(row.get("major_regressions", 0) or 0)),
                contradiction_losses=max(0, int(row.get("contradiction_losses", 0) or 0)),
                conflict_lesson_ids=tuple(sorted({str(v).strip() for v in row.get("conflict_lesson_ids", []) if str(v).strip()})),
                archived_reason=str(row.get("archived_reason", "")).strip() or None,
                created_at=str(row.get("created_at", "")).strip() or _utc_now_iso(),
                updated_at=str(row.get("updated_at", "")).strip() or _utc_now_iso(),
            )

        # Legacy lesson row adapter.
        lesson_text = " ".join(str(row.get("lesson", "")).split())
        if not lesson_text:
            return None
        session_id = 0
        try:
            session_id = int(row.get("session_id", 0) or 0)
        except (TypeError, ValueError):
            session_id = 0
        try:
            eval_score = float(row.get("eval_score", 0.0) or 0.0)
        except (TypeError, ValueError):
            eval_score = 0.0
        reliability = _clamp(0.35 + (0.55 * eval_score), 0.05, 0.95)
        fingerprints = tuple(sorted({str(v).strip() for v in row.get("trigger_fingerprints", []) if str(v).strip()}))
        normalized_rule = normalize_rule_text(lesson_text)
        lesson_id = _stable_lesson_id(normalized_rule=normalized_rule, trigger_fingerprints=fingerprints)
        timestamp = str(row.get("timestamp", "")).strip() or _utc_now_iso()
        return cls(
            lesson_id=lesson_id,
            status="promoted",
            rule_text=lesson_text[:420],
            normalized_rule=normalized_rule,
            trigger_fingerprints=fingerprints,
            tags=_extract_tags_from_text(lesson_text),
            task_id=str(row.get("task_id", "")).strip(),
            task=str(row.get("task", "")).strip(),
            domain=str(row.get("domain", "")).strip(),
            source_session_ids=(session_id,) if session_id > 0 else (),
            reliability=reliability,
            retrieval_count=0,
            helpful_count=0,
            harmful_count=0,
            utility_history=(),
            major_regressions=0,
            contradiction_losses=0,
            conflict_lesson_ids=(),
            archived_reason=None,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def to_row(self) -> dict[str, Any]:
        """
        Write V2 rows with legacy compatibility fields.

        Keeping legacy fields allows existing readers of `lessons.jsonl` to
        continue operating during rollout without a hard migration cutover.
        """
        return {
            # Legacy-compatible fields.
            "session_id": self.source_session_ids[-1] if self.source_session_ids else 0,
            "task_id": self.task_id,
            "task": self.task,
            "category": "insight",
            "lesson": self.rule_text,
            "evidence_steps": [],
            "eval_passed": self.status == "promoted",
            "eval_score": round(self.reliability, 4),
            "skill_refs_used": [],
            "timestamp": self.updated_at,
            # V2 fields.
            "memory_schema": V2_SCHEMA,
            "memory_schema_version": V2_VERSION,
            "lesson_id": self.lesson_id,
            "status": self.status,
            "rule_text": self.rule_text,
            "normalized_rule": self.normalized_rule,
            "trigger_fingerprints": list(self.trigger_fingerprints),
            "tags": list(self.tags),
            "domain": self.domain,
            "source_session_ids": list(self.source_session_ids),
            "reliability": round(float(self.reliability), 4),
            "retrieval_count": int(self.retrieval_count),
            "helpful_count": int(self.helpful_count),
            "harmful_count": int(self.harmful_count),
            "utility_history": [round(float(v), 6) for v in self.utility_history],
            "major_regressions": int(self.major_regressions),
            "contradiction_losses": int(self.contradiction_losses),
            "conflict_lesson_ids": list(self.conflict_lesson_ids),
            "archived_reason": self.archived_reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def load_lesson_records(path: Path) -> list[LessonRecord]:
    if not path.exists():
        return []
    records: list[LessonRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError:
            continue
        record = LessonRecord.from_row(row)
        if record is not None:
            records.append(record)
    return records


def write_lesson_records(path: Path, records: Sequence[LessonRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.to_row(), ensure_ascii=True) + "\n")


def _is_conflict_text(a: str, b: str) -> bool:
    """Heuristic contradiction check for lessons sharing the same trigger."""
    a_norm = normalize_rule_text(a)
    b_norm = normalize_rule_text(b)
    toggles = (
        ("must", "must not"),
        ("requires", "does not require"),
        ("use", "do not use"),
        ("lowercase", "uppercase"),
        ("quoted", "unquoted"),
    )
    for positive, negative in toggles:
        if positive in a_norm and negative in b_norm:
            return True
        if positive in b_norm and negative in a_norm:
            return True
    return False


def _merge_records(existing: LessonRecord, incoming: LessonRecord) -> LessonRecord:
    """Merge duplicate lessons while preserving stronger reliability evidence."""
    source_ids = tuple(sorted(set(existing.source_session_ids) | set(incoming.source_session_ids)))
    trigger_fps = tuple(sorted(set(existing.trigger_fingerprints) | set(incoming.trigger_fingerprints)))
    tags = tuple(sorted(set(existing.tags) | set(incoming.tags)))
    now = _utc_now_iso()
    status = existing.status
    if existing.status in {"candidate", "suppressed"} and incoming.status == "promoted":
        status = "promoted"
    if existing.status == "archived":
        status = "archived"
    reliability = max(existing.reliability, incoming.reliability)
    return LessonRecord(
        lesson_id=existing.lesson_id,
        status=status,
        rule_text=existing.rule_text if len(existing.rule_text) >= len(incoming.rule_text) else incoming.rule_text,
        normalized_rule=existing.normalized_rule,
        trigger_fingerprints=trigger_fps,
        tags=tags,
        task_id=existing.task_id or incoming.task_id,
        task=existing.task or incoming.task,
        domain=existing.domain or incoming.domain,
        source_session_ids=source_ids,
        reliability=_clamp(reliability, 0.0, 1.0),
        retrieval_count=max(existing.retrieval_count, incoming.retrieval_count),
        helpful_count=max(existing.helpful_count, incoming.helpful_count),
        harmful_count=max(existing.harmful_count, incoming.harmful_count),
        utility_history=existing.utility_history if len(existing.utility_history) >= len(incoming.utility_history) else incoming.utility_history,
        major_regressions=max(existing.major_regressions, incoming.major_regressions),
        contradiction_losses=max(existing.contradiction_losses, incoming.contradiction_losses),
        conflict_lesson_ids=tuple(sorted(set(existing.conflict_lesson_ids) | set(incoming.conflict_lesson_ids))),
        archived_reason=existing.archived_reason or incoming.archived_reason,
        created_at=existing.created_at,
        updated_at=now,
    )


def _link_conflicts(records: Sequence[LessonRecord]) -> tuple[list[LessonRecord], int]:
    updated = list(records)
    links = 0
    for i, left in enumerate(updated):
        left_conflicts = set(left.conflict_lesson_ids)
        for j, right in enumerate(updated):
            if i >= j:
                continue
            same_trigger = bool(set(left.trigger_fingerprints) & set(right.trigger_fingerprints))
            if not same_trigger:
                continue
            if not _is_conflict_text(left.rule_text, right.rule_text):
                continue
            left_conflicts.add(right.lesson_id)
            right_conflicts = set(updated[j].conflict_lesson_ids)
            right_conflicts.add(left.lesson_id)
            updated[j] = LessonRecord(**{**updated[j].__dict__, "conflict_lesson_ids": tuple(sorted(right_conflicts))})
            links += 1
        updated[i] = LessonRecord(**{**left.__dict__, "conflict_lesson_ids": tuple(sorted(left_conflicts))})
    return updated, links


def upsert_lesson_records(path: Path, new_records: Sequence[LessonRecord]) -> dict[str, int]:
    """Insert/merge records with dedup + conflict-link refresh."""
    existing = load_lesson_records(path)
    by_identity: dict[tuple[str, tuple[str, ...]], LessonRecord] = {
        (rec.normalized_rule, rec.trigger_fingerprints): rec for rec in existing
    }
    inserted = 0
    merged = 0
    for incoming in new_records:
        key = (incoming.normalized_rule, incoming.trigger_fingerprints)
        current = by_identity.get(key)
        if current is None:
            by_identity[key] = incoming
            inserted += 1
        else:
            by_identity[key] = _merge_records(current, incoming)
            merged += 1
    refreshed, conflict_links = _link_conflicts(list(by_identity.values()))
    write_lesson_records(path, refreshed)
    return {"inserted": inserted, "merged": merged, "conflict_links": conflict_links, "total": len(refreshed)}


def archive_lessons(path: Path, *, lesson_ids: Iterable[str], reason: str) -> int:
    ids = {str(value).strip() for value in lesson_ids if str(value).strip()}
    if not ids:
        return 0
    records = load_lesson_records(path)
    changed = 0
    now = _utc_now_iso()
    archived_rows: list[LessonRecord] = []
    for record in records:
        if record.lesson_id not in ids:
            archived_rows.append(record)
            continue
        changed += 1
        archived_rows.append(
            LessonRecord(
                **{
                    **record.__dict__,
                    "status": "archived",
                    "archived_reason": str(reason).strip() or "archived",
                    "updated_at": now,
                }
            )
        )
    if changed:
        write_lesson_records(path, archived_rows)
    return changed


def migrate_legacy_lessons(*, legacy_path: Path, v2_path: Path) -> dict[str, int]:
    """
    Idempotent migration helper from `lessons.jsonl` into V2 store.

    It can be run on every session startup: dedup keeps migration cheap and
    avoids requiring explicit one-off migration scripts during experiments.
    """
    legacy = load_lesson_records(legacy_path)
    if not legacy:
        return {"inserted": 0, "merged": 0, "conflict_links": 0, "total": len(load_lesson_records(v2_path))}
    return upsert_lesson_records(v2_path, legacy)


__all__ = [
    "LESSON_STATUSES",
    "LessonRecord",
    "archive_lessons",
    "load_lesson_records",
    "migrate_legacy_lessons",
    "normalize_rule_text",
    "upsert_lesson_records",
    "write_lesson_records",
]
