from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LESSONS_PATH = Path("learning/lessons.jsonl")
ALLOWED_CATEGORIES = {"mistake", "insight", "shortcut", "ui_detail"}
PERMISSION_NOISE_TERMS = (
    "permission",
    "accessibility",
    "axisprocesstrusted",
    "cgpreflightposteventaccess",
    "window not found",
)


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
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


@dataclass(frozen=True)
class Lesson:
    session_id: int
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
            "task": self.task,
            "category": self.category,
            "lesson": self.lesson,
            "evidence_steps": self.evidence_steps,
            "eval_passed": self.eval_passed,
            "eval_score": self.eval_score,
            "skill_refs_used": self.skill_refs_used,
            "timestamp": self.timestamp,
        }


def load_lessons(*, path: Path = LESSONS_PATH) -> list[Lesson]:
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
        category = str(row.get("category", "insight")).strip().lower()
        if category not in ALLOWED_CATEGORIES:
            category = "insight"
        lesson = " ".join(str(row.get("lesson", "")).split())
        if not lesson:
            continue
        raw_steps = row.get("evidence_steps", [])
        steps: list[int] = []
        if isinstance(raw_steps, list):
            for s in raw_steps:
                if isinstance(s, int) and s > 0:
                    steps.append(s)
        raw_refs = row.get("skill_refs_used", [])
        refs = [str(r).strip() for r in raw_refs if isinstance(r, str) and str(r).strip()]
        try:
            session_id = int(row.get("session_id", 0))
        except (TypeError, ValueError):
            session_id = 0
        try:
            eval_score = float(row.get("eval_score", 0.0))
        except (TypeError, ValueError):
            eval_score = 0.0
        lessons.append(
            Lesson(
                session_id=max(0, session_id),
                task=str(row.get("task", "")).strip(),
                category=category,
                lesson=lesson,
                evidence_steps=steps[:8],
                eval_passed=bool(row.get("eval_passed", False)),
                eval_score=eval_score,
                skill_refs_used=refs[:8],
                timestamp=str(row.get("timestamp", "")) or datetime.now(timezone.utc).isoformat(),
            )
        )
    return lessons


def store_lessons(
    lessons: list[Lesson],
    *,
    path: Path = LESSONS_PATH,
) -> int:
    if not lessons:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for lesson in lessons:
            f.write(json.dumps(lesson.to_dict(), ensure_ascii=True) + "\n")
    return len(lessons)


def _score_lesson_relevance(task: str, lesson: Lesson) -> float:
    score = _jaccard(task, lesson.task) + (0.6 * _jaccard(task, lesson.lesson))
    if "fl studio" in task.lower() and "fl studio" in lesson.task.lower():
        score += 0.15
    if "drum" in task.lower() and ("drum" in lesson.task.lower() or "kick" in lesson.lesson.lower()):
        score += 0.15
    return score


def _is_permission_noise(lesson: Lesson) -> bool:
    text = f"{lesson.task} {lesson.lesson}".lower()
    return any(tok in text for tok in PERMISSION_NOISE_TERMS)


def _lesson_quality_score(lesson: Lesson) -> float:
    quality = float(lesson.eval_score)
    if lesson.eval_passed:
        quality += 0.25
    if _is_permission_noise(lesson):
        quality -= 0.4
    return quality


def load_relevant_lessons(
    task: str,
    *,
    max_lessons: int = 10,
    max_sessions: int = 5,
    path: Path = LESSONS_PATH,
) -> tuple[str, int]:
    all_lessons = load_lessons(path=path)
    if not all_lessons:
        return "No prior lessons loaded.", 0

    scored: list[tuple[float, Lesson]] = []
    task_lower = task.lower()
    for lesson in all_lessons:
        # Avoid stale environment blockers being replayed in normal FL runs.
        if "fl studio" in task_lower and _is_permission_noise(lesson) and "permission" not in task_lower:
            continue
        rel = _score_lesson_relevance(task, lesson)
        quality = _lesson_quality_score(lesson)
        if rel > 0:
            if quality < 0.0:
                continue
            scored.append((rel + (0.25 * quality), lesson))
    if not scored:
        return "No prior lessons loaded.", 0

    scored.sort(key=lambda item: (item[0], item[1].timestamp), reverse=True)

    selected: list[Lesson] = []
    used_sessions: set[int] = set()
    selected_texts: list[str] = []
    for _, lesson in scored:
        if lesson.session_id and len(used_sessions) >= max_sessions and lesson.session_id not in used_sessions:
            continue
        if any(_jaccard(lesson.lesson, seen) > 0.86 for seen in selected_texts):
            continue
        selected.append(lesson)
        selected_texts.append(lesson.lesson)
        if lesson.session_id:
            used_sessions.add(lesson.session_id)
        if len(selected) >= max_lessons:
            break

    if not selected:
        return "No prior lessons loaded.", 0

    lines = ["Lessons from previous sessions (apply only when relevant):"]
    for lesson in selected:
        step_text = ",".join(str(s) for s in lesson.evidence_steps[:4]) if lesson.evidence_steps else "-"
        lines.append(
            f"- [{lesson.category}] {lesson.lesson} "
            f"(session={lesson.session_id}, score={lesson.eval_score:.2f}, steps={step_text})"
        )
    return "\n".join(lines), len(selected)


def generate_lessons(
    *,
    client: Any,
    model: str,
    session_id: int,
    task: str,
    eval_result: dict[str, Any],
    events_tail: list[dict[str, Any]],
    skill_refs_used: list[str],
) -> list[Lesson]:
    try:
        score = float(eval_result.get("score", 0.0))
    except (TypeError, ValueError):
        score = 0.0
    passed = bool(eval_result.get("passed", False))
    if passed and score >= 1.0:
        return []

    system = (
        "You are a post-run learning critic.\n"
        "Return STRICT JSON array only. Each item:\n"
        '{"category":"mistake|insight|shortcut|ui_detail","lesson":"...","evidence_steps":[1,2]}\n'
        "Rules:\n"
        "- Be specific and concise.\n"
        "- No generic advice.\n"
        "- Only use evidence from provided events/eval.\n"
        "- 1 to 4 lessons total.\n"
    )
    user = (
        "TASK:\n"
        f"{task}\n\n"
        "EVAL:\n"
        f"{json.dumps(eval_result, ensure_ascii=True)}\n\n"
        "EVENTS_TAIL:\n"
        f"{json.dumps(events_tail, ensure_ascii=True)}\n\n"
        "SKILLS_USED:\n"
        f"{json.dumps(skill_refs_used, ensure_ascii=True)}"
    )

    try:
        resp = client.messages.create(
            model=model,
            max_tokens=500,
            system=system,
            messages=[{"role": "user", "content": [{"type": "text", "text": user}]}],
        )
    except Exception:
        return []

    raw = ""
    for b in resp.content:
        bd = b.model_dump() if hasattr(b, "model_dump") else b  # type: ignore[attr-defined]
        if isinstance(bd, dict) and bd.get("type") == "text":
            raw += str(bd.get("text", ""))

    parsed = _extract_json_array(raw)
    out: list[Lesson] = []
    now = datetime.now(timezone.utc).isoformat()
    for item in parsed[:4]:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category", "insight")).strip().lower()
        if category not in ALLOWED_CATEGORIES:
            category = "insight"
        lesson = " ".join(str(item.get("lesson", "")).split())
        if not lesson:
            continue
        raw_steps = item.get("evidence_steps", [])
        steps: list[int] = []
        if isinstance(raw_steps, list):
            for s in raw_steps:
                if isinstance(s, int) and s > 0:
                    steps.append(s)
        out.append(
            Lesson(
                session_id=session_id,
                task=task,
                category=category,
                lesson=lesson[:280],
                evidence_steps=sorted(set(steps))[:8],
                eval_passed=passed,
                eval_score=score,
                skill_refs_used=skill_refs_used[:8],
                timestamp=now,
            )
        )
    return out
