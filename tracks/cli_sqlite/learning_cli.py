from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ALLOWED_CATEGORIES = {"mistake", "insight", "shortcut", "sql_detail"}
REASON_LESSON_TEMPLATES: dict[str, tuple[str, str]] = {
    "missing_required_pattern": (
        "mistake",
        "reason_code=missing_required_pattern; anti_pattern=missing mandatory SQL phases; "
        "fix=execute required statements explicitly and verify contract before stopping.",
    ),
    "matched_forbidden_pattern": (
        "mistake",
        "reason_code=matched_forbidden_pattern; anti_pattern=using forbidden SQL operation; "
        "fix=replace forbidden statements with safe transaction flow and rerun verify_contract.",
    ),
    "required_query_mismatch": (
        "sql_detail",
        "reason_code=required_query_mismatch; anti_pattern=final state does not satisfy required queries; "
        "fix=run required verification queries and reconcile row counts before completion.",
    ),
    "too_many_errors": (
        "shortcut",
        "reason_code=too_many_errors; anti_pattern=continuing writes after repeated SQL errors; "
        "fix=after first error, inspect schema/state and repair plan before next mutation.",
    ),
}


def _tokenize(text: str) -> set[str]:
    normalized = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    return {tok for tok in normalized.split() if tok}


def _jaccard(a: str, b: str) -> float:
    ta = _tokenize(a)
    tb = _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / float(len(ta | tb))


def _extract_json_array(raw: str) -> list[dict[str, Any]]:
    text = raw.strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _reason_evidence_steps(reason: str, events_tail: list[dict[str, Any]]) -> list[int]:
    reason_lower = reason.lower()
    steps: list[int] = []
    for row in events_tail:
        if not isinstance(row, dict):
            continue
        step = row.get("step")
        if not isinstance(step, int) or step <= 0:
            continue
        if bool(row.get("ok", True)):
            continue
        error = str(row.get("error", "")).lower()
        if reason_lower == "too_many_errors":
            steps.append(step)
            continue
        if reason_lower == "required_query_mismatch" and ("constraint" in error or "parse error" in error):
            steps.append(step)
            continue
        if reason_lower == "matched_forbidden_pattern" and ("forbidden" in error or "blocked" in error):
            steps.append(step)
            continue
        if reason_lower == "missing_required_pattern" and ("missing" in error or "syntax" in error):
            steps.append(step)
            continue
    return sorted(set(steps))[:8]


@dataclass(frozen=True)
class Lesson:
    session_id: int
    task_id: str
    task: str
    category: str
    lesson: str
    evidence_steps: list[int]
    eval_passed: bool
    eval_score: float
    skill_refs_used: list[str]
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "task_id": self.task_id,
            "task": self.task,
            "category": self.category,
            "lesson": self.lesson,
            "evidence_steps": self.evidence_steps,
            "eval_passed": self.eval_passed,
            "eval_score": self.eval_score,
            "skill_refs_used": self.skill_refs_used,
            "timestamp": self.timestamp,
        }


def load_lessons(path: Path) -> list[Lesson]:
    if not path.exists():
        return []
    lessons: list[Lesson] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        lesson_text = " ".join(str(row.get("lesson", "")).split())
        if not lesson_text:
            continue
        category = str(row.get("category", "insight")).strip().lower()
        if category not in ALLOWED_CATEGORIES:
            category = "insight"
        steps_raw = row.get("evidence_steps", [])
        steps = [int(step) for step in steps_raw if isinstance(step, int) and step > 0][:8] if isinstance(steps_raw, list) else []
        refs_raw = row.get("skill_refs_used", [])
        refs = [str(ref).strip() for ref in refs_raw if isinstance(ref, str) and str(ref).strip()][:8] if isinstance(refs_raw, list) else []
        try:
            session_id = max(0, int(row.get("session_id", 0)))
        except (TypeError, ValueError):
            session_id = 0
        try:
            eval_score = float(row.get("eval_score", 0.0))
        except (TypeError, ValueError):
            eval_score = 0.0
        lessons.append(
            Lesson(
                session_id=session_id,
                task_id=str(row.get("task_id", "")).strip(),
                task=str(row.get("task", "")).strip(),
                category=category,
                lesson=lesson_text[:280],
                evidence_steps=steps,
                eval_passed=bool(row.get("eval_passed", False)),
                eval_score=eval_score,
                skill_refs_used=refs,
                timestamp=str(row.get("timestamp", "")) or datetime.now(timezone.utc).isoformat(),
            )
        )
    return lessons


def store_lessons(*, path: Path, lessons: list[Lesson]) -> int:
    if not lessons:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for lesson in lessons:
            f.write(json.dumps(lesson.to_dict(), ensure_ascii=True) + "\n")
    return len(lessons)


def load_relevant_lessons(
    *,
    path: Path,
    task_id: str,
    task: str,
    max_lessons: int = 8,
    max_sessions: int = 5,
) -> tuple[str, int]:
    all_lessons = load_lessons(path)
    if not all_lessons:
        return "No prior lessons loaded.", 0

    scored: list[tuple[float, Lesson]] = []
    for lesson in all_lessons:
        score = _jaccard(task, lesson.task) + (0.6 * _jaccard(task, lesson.lesson))
        if lesson.task_id == task_id:
            score += 0.3
        if score > 0:
            scored.append((score, lesson))
    scored.sort(key=lambda item: (item[0], item[1].timestamp), reverse=True)

    selected: list[Lesson] = []
    seen_sessions: set[int] = set()
    for _, lesson in scored:
        if lesson.session_id and len(seen_sessions) >= max_sessions and lesson.session_id not in seen_sessions:
            continue
        selected.append(lesson)
        if lesson.session_id:
            seen_sessions.add(lesson.session_id)
        if len(selected) >= max_lessons:
            break
    if not selected:
        return "No prior lessons loaded.", 0

    lines = ["Lessons from previous CLI sessions (apply only when relevant):"]
    for lesson in selected:
        step_text = ",".join(str(step) for step in lesson.evidence_steps[:4]) if lesson.evidence_steps else "-"
        lines.append(
            f"- [{lesson.category}] {lesson.lesson} "
            f"(task_id={lesson.task_id}, session={lesson.session_id}, score={lesson.eval_score:.2f}, steps={step_text})"
        )
    return "\n".join(lines), len(selected)


def generate_lessons(
    *,
    client: Any,
    model: str,
    session_id: int,
    task_id: str,
    task: str,
    eval_result: dict[str, Any],
    events_tail: list[dict[str, Any]],
    skill_refs_used: list[str],
) -> list[Lesson]:
    # Client/model are kept in signature for backward compatibility with caller interface.
    _ = client
    _ = model
    passed = bool(eval_result.get("passed", False))
    try:
        score = float(eval_result.get("score", 0.0))
    except (TypeError, ValueError):
        score = 0.0
    if passed and score >= 1.0:
        return []
    now = datetime.now(timezone.utc).isoformat()
    lessons: list[Lesson] = []

    reasons = eval_result.get("reasons", [])
    if not isinstance(reasons, list):
        reasons = []
    for reason in reasons[:4]:
        if not isinstance(reason, str):
            continue
        template = REASON_LESSON_TEMPLATES.get(reason)
        if template is None:
            continue
        category, lesson_text = template
        steps = _reason_evidence_steps(reason, events_tail)
        if not steps:
            # If no precise evidence mapping, still anchor lesson to recent failed steps.
            recent_failed = [
                int(row.get("step"))
                for row in events_tail
                if isinstance(row, dict) and isinstance(row.get("step"), int) and not bool(row.get("ok", True))
            ]
            steps = sorted(set(recent_failed))[:8]
        lessons.append(
            Lesson(
                session_id=session_id,
                task_id=task_id,
                task=task,
                category=category,
                lesson=lesson_text[:280],
                evidence_steps=sorted(set(steps)),
                eval_passed=passed,
                eval_score=score,
                skill_refs_used=skill_refs_used[:8],
                timestamp=now,
            )
        )
    if lessons:
        return lessons

    # Fallback deterministic lesson for unknown reason codes.
    fallback_steps = sorted(
        {
            int(row.get("step"))
            for row in events_tail
            if isinstance(row, dict) and isinstance(row.get("step"), int) and not bool(row.get("ok", True))
        }
    )[:8]
    lessons.append(
        Lesson(
            session_id=session_id,
            task_id=task_id,
            task=task,
            category="insight",
            lesson=(
                "reason_code=unknown_failure; anti_pattern=run ended without contract pass; "
                "fix=run verify_contract, inspect failed checks, and apply minimal SQL correction before stopping."
            ),
            evidence_steps=fallback_steps,
            eval_passed=passed,
            eval_score=score,
            skill_refs_used=skill_refs_used[:8],
            timestamp=now,
        )
    )
    return lessons
