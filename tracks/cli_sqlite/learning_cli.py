from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ALLOWED_CATEGORIES = {"mistake", "insight", "shortcut", "sql_detail"}


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


def store_lessons(*, path: Path, lessons: list[Lesson], dedup_threshold: float = 0.65) -> int:
    if not lessons:
        return 0
    existing = load_lessons(path) if path.exists() else []
    stored = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for lesson in lessons:
            existing_for_task = [ex for ex in existing if ex.task_id == lesson.task_id]
            if any(_jaccard(lesson.lesson, ex.lesson) >= dedup_threshold for ex in existing_for_task):
                continue
            f.write(json.dumps(lesson.to_dict(), ensure_ascii=True) + "\n")
            existing.append(lesson)
            stored += 1
    return stored


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


_GENERIC_PATTERNS = re.compile(
    r"(?i)\b("
    r"always read the skill|"
    r"be careful|"
    r"remember to|"
    r"don'?t forget|"
    r"make sure to read|"
    r"always check|"
    r"read the documentation|"
    r"pay attention to|"
    r"take care when|"
    r"be mindful"
    r")\b"
)

_SQL_KEYWORDS = re.compile(
    r"(?i)\b("
    r"SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|BEGIN|COMMIT|ROLLBACK|"
    r"ON CONFLICT|GROUP BY|ORDER BY|WHERE|JOIN|PRIMARY KEY|FOREIGN KEY|"
    r"INTEGER|TEXT|REAL|BLOB|NULL|NOT NULL|UNIQUE|INDEX|TRANSACTION|"
    r"SUM|COUNT|AVG|MAX|MIN|HAVING|DISTINCT|UNION|EXCEPT|INTERSECT|"
    r"VALUES|INTO|FROM|TABLE|VIEW|TRIGGER|"
    r"fixture_seed|ledger|rejects|checkpoint_log|sales|error_log|inventory"
    r")\b"
)

_STEP_REFERENCE = re.compile(r"(?i)\b(?:step\s*\d+|at step|steps?\s*[\d,]+)\b")
_ERROR_REFERENCE = re.compile(r"(?i)(?:error|exception|failed|missing|duplicate|mismatch|constraint|violation)")


def _lesson_quality_score(lesson: Lesson) -> float:
    text = lesson.lesson
    if _GENERIC_PATTERNS.search(text):
        return 0.0
    score = 0.0
    sql_matches = len(_SQL_KEYWORDS.findall(text))
    score += min(sql_matches * 0.15, 0.45)
    if _STEP_REFERENCE.search(text):
        score += 0.2
    if _ERROR_REFERENCE.search(text):
        score += 0.2
    if lesson.evidence_steps:
        score += 0.15
    return min(score, 1.0)


def filter_lessons(lessons: list[Lesson], *, min_quality: float = 0.15) -> list[Lesson]:
    return [lesson for lesson in lessons if _lesson_quality_score(lesson) >= min_quality]


def prune_lessons(path: Path, *, max_per_task: int = 20) -> int:
    all_lessons = load_lessons(path)
    if not all_lessons:
        return 0
    by_task: dict[str, list[Lesson]] = {}
    for lesson in all_lessons:
        by_task.setdefault(lesson.task_id, []).append(lesson)

    pruned = False
    kept: list[Lesson] = []
    for task_id, task_lessons in by_task.items():
        if len(task_lessons) <= max_per_task:
            kept.extend(task_lessons)
        else:
            scored = sorted(task_lessons, key=_lesson_quality_score, reverse=True)
            kept.extend(scored[:max_per_task])
            pruned = True

    if not pruned:
        return 0
    removed = len(all_lessons) - len(kept)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for lesson in kept:
            f.write(json.dumps(lesson.to_dict(), ensure_ascii=True) + "\n")
    return removed


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
    passed = bool(eval_result.get("passed", False))
    try:
        score = float(eval_result.get("score", 0.0))
    except (TypeError, ValueError):
        score = 0.0
    if passed and score >= 1.0:
        return []

    system = (
        "You are a post-run SQL learning critic.\n"
        "Return STRICT JSON array only. Each item must match:\n"
        '{"category":"mistake|insight|shortcut|sql_detail","lesson":"...","evidence_steps":[1,2]}\n'
        "Rules:\n"
        "- Each lesson MUST reference at least one of: exact SQL fragment, error message, step number, or column/table name.\n"
        "- REJECT generic advice like 'always read the skill', 'be careful with SQL', 'remember to check'.\n"
        "- Good: 'INSERT INTO ledger missed ON CONFLICT for event_id causing duplicate at step 4'\n"
        "- Bad: 'Always read the skill document before executing SQL'\n"
        "- Base lessons only on provided events and deterministic eval.\n"
        "- 1 to 4 lessons total.\n"
    )
    user = (
        f"TASK_ID:\n{task_id}\n\n"
        f"TASK:\n{task}\n\n"
        f"EVAL:\n{json.dumps(eval_result, ensure_ascii=True)}\n\n"
        f"EVENTS_TAIL:\n{json.dumps(events_tail, ensure_ascii=True)}\n\n"
        f"SKILLS_USED:\n{json.dumps(skill_refs_used, ensure_ascii=True)}"
    )

    try:
        response = client.messages.create(
            model=model,
            max_tokens=500,
            system=system,
            messages=[{"role": "user", "content": [{"type": "text", "text": user}]}],
        )
    except Exception:
        return []

    raw = ""
    for block in response.content:
        data = block.model_dump() if hasattr(block, "model_dump") else block  # type: ignore[attr-defined]
        if isinstance(data, dict) and data.get("type") == "text":
            raw += str(data.get("text", ""))

    parsed = _extract_json_array(raw)
    now = datetime.now(timezone.utc).isoformat()
    lessons: list[Lesson] = []
    for item in parsed[:4]:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category", "insight")).strip().lower()
        if category not in ALLOWED_CATEGORIES:
            category = "insight"
        lesson_text = " ".join(str(item.get("lesson", "")).split())
        if not lesson_text:
            continue
        raw_steps = item.get("evidence_steps", [])
        steps = [int(step) for step in raw_steps if isinstance(step, int) and step > 0][:8] if isinstance(raw_steps, list) else []
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
    return filter_lessons(lessons)
