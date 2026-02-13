from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tracks.cli_sqlite.skill_routing_cli import SkillManifestEntry, build_skill_manifest


def _tokenize(text: str) -> set[str]:
    return {tok for tok in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split() if tok}


def _jaccard(a: str, b: str) -> float:
    ta = _tokenize(a)
    tb = _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / float(len(ta | tb))


@dataclass(frozen=True)
class ReplaceRule:
    find: str
    replace: str


@dataclass(frozen=True)
class SkillUpdate:
    skill_ref: str
    skill_digest: str
    root_cause: str
    evidence_steps: list[int]
    replace_rules: list[ReplaceRule]
    append_bullets: list[str]


def skill_digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if not text:
        return None
    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_reflection_response(raw: str) -> tuple[list[SkillUpdate], float]:
    obj = _extract_json_object(raw)
    if obj is None:
        return [], 0.0
    confidence = float(obj.get("confidence", 0.0) or 0.0)
    updates_raw = obj.get("skill_updates")
    if not isinstance(updates_raw, list):
        return [], confidence

    updates: list[SkillUpdate] = []
    for item in updates_raw:
        if not isinstance(item, dict):
            continue
        skill_ref = item.get("skill_ref")
        digest = item.get("skill_digest")
        root_cause = item.get("root_cause")
        steps_raw = item.get("evidence_steps", [])
        if not isinstance(skill_ref, str) or not isinstance(digest, str) or not isinstance(root_cause, str):
            continue
        if not isinstance(steps_raw, list):
            continue
        steps = [int(step) for step in steps_raw if isinstance(step, int) and step > 0][:8]
        if not steps:
            continue

        replace_rules_raw = item.get("replace_rules", [])
        replace_rules: list[ReplaceRule] = []
        if isinstance(replace_rules_raw, list):
            for rule in replace_rules_raw[:5]:
                if not isinstance(rule, dict):
                    continue
                find = rule.get("find")
                replace = rule.get("replace")
                if not isinstance(find, str) or not isinstance(replace, str):
                    continue
                find = " ".join(find.split())
                replace = " ".join(replace.split())
                if not find or not replace:
                    continue
                replace_rules.append(ReplaceRule(find=find, replace=replace))

        append_raw = item.get("append_bullets", [])
        append_bullets: list[str] = []
        if isinstance(append_raw, list):
            for bullet in append_raw[:5]:
                if not isinstance(bullet, str):
                    continue
                normalized = " ".join(bullet.split())
                if normalized:
                    append_bullets.append(normalized[:220])

        if not replace_rules and not append_bullets:
            continue
        updates.append(
            SkillUpdate(
                skill_ref=skill_ref.strip(),
                skill_digest=digest.strip().lower(),
                root_cause=" ".join(root_cause.split())[:400],
                evidence_steps=steps,
                replace_rules=replace_rules,
                append_bullets=append_bullets,
            )
        )
    return updates, confidence


def propose_skill_updates(
    *,
    client: Any,
    model: str,
    task: str,
    metrics: dict[str, Any],
    eval_result: dict[str, Any],
    events_tail: list[dict[str, Any]],
    routed_skill_refs: list[str],
    read_skill_refs: list[str],
    skill_snapshots: list[str],
) -> tuple[list[SkillUpdate], float, str]:
    system = (
        "You are PostTaskHook for SQL skill maintenance.\n"
        "Return STRICT JSON only:\n"
        "{\n"
        '  "confidence": 0.0,\n'
        '  "skill_updates": [\n'
        "    {\n"
        '      "skill_ref": "...",\n'
        '      "skill_digest": "...",\n'
        '      "root_cause": "...",\n'
        '      "evidence_steps": [2,4],\n'
        '      "replace_rules": [{"find":"...","replace":"..."}],\n'
        '      "append_bullets": ["..."]\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules:\n"
        "- Use deterministic eval as primary signal.\n"
        "- If eval passed=true, return no updates.\n"
        "- Do not repeat existing skill guidance.\n"
        "- Max 2 skills, max 3 bullets per skill.\n"
    )
    user = (
        f"TASK:\n{task}\n\n"
        f"METRICS:\n{json.dumps(metrics, ensure_ascii=True)}\n\n"
        f"EVAL:\n{json.dumps(eval_result, ensure_ascii=True)}\n\n"
        f"EVENTS_TAIL:\n{json.dumps(events_tail, ensure_ascii=True)}\n\n"
        f"ROUTED_SKILLS:\n{json.dumps(routed_skill_refs, ensure_ascii=True)}\n\n"
        f"READ_SKILLS:\n{json.dumps(read_skill_refs, ensure_ascii=True)}\n\n"
        f"SKILL_SNAPSHOTS:\n{json.dumps(skill_snapshots, ensure_ascii=True)}"
    )

    try:
        response = client.messages.create(
            model=model,
            max_tokens=900,
            system=system,
            messages=[{"role": "user", "content": [{"type": "text", "text": user}]}],
        )
    except Exception as exc:
        return [], 0.0, f"critic_call_failed:{type(exc).__name__}"

    raw = ""
    for block in response.content:
        data = block.model_dump() if hasattr(block, "model_dump") else block  # type: ignore[attr-defined]
        if isinstance(data, dict) and data.get("type") == "text":
            raw += str(data.get("text", ""))
    updates, confidence = parse_reflection_response(raw)
    return updates, confidence, raw


def _parse_frontmatter(text: str) -> tuple[dict[str, str], tuple[int, int] | None]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, None
    end = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end is None:
        return {}, None

    meta: dict[str, str] = {}
    for line in lines[1:end]:
        stripped = line.strip()
        if not stripped or ":" not in stripped or stripped.startswith("#"):
            continue
        key, value = stripped.split(":", 1)
        meta[key.strip()] = value.strip().strip('"').strip("'")
    span_end = sum(len(ln) for ln in lines[: end + 1])
    return meta, (0, span_end)


def _render_frontmatter(meta: dict[str, str]) -> str:
    preferred = ["name", "description", "version"]
    out = ["---\n"]
    for key in preferred:
        value = str(meta.get(key, "")).strip()
        if value:
            out.append(f"{key}: {value}\n")
    for key in sorted(meta.keys()):
        if key in preferred:
            continue
        value = str(meta.get(key, "")).strip()
        if value:
            out.append(f"{key}: {value}\n")
    out.append("---\n")
    return "".join(out)


def apply_skill_updates(
    *,
    entries: list[SkillManifestEntry],
    updates: list[SkillUpdate],
    confidence: float,
    skills_root: Path,
    manifest_path: Path,
    min_confidence: float = 0.7,
    max_skills: int = 2,
    required_skill_digests: dict[str, str] | None = None,
    allowed_skill_refs: set[str] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "attempted": bool(updates),
        "applied": 0,
        "updated_skill_refs": [],
        "confidence": confidence,
        "skipped_reason": None,
    }
    if not updates:
        result["skipped_reason"] = "no_updates"
        return result
    if confidence < min_confidence:
        result["skipped_reason"] = f"low_confidence<{min_confidence}"
        return result

    by_ref = {entry.skill_ref: entry for entry in entries}
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for update in updates[:max_skills]:
        entry = by_ref.get(update.skill_ref)
        if entry is None:
            continue
        if allowed_skill_refs is not None and update.skill_ref not in allowed_skill_refs:
            continue
        if required_skill_digests is not None:
            expected = required_skill_digests.get(update.skill_ref, "")
            if not expected or expected.lower() != update.skill_digest.lower():
                continue

        path = Path(entry.path)
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if required_skill_digests is not None:
            actual_digest = skill_digest(text).lower()
            expected_digest = required_skill_digests.get(update.skill_ref, "").lower()
            if expected_digest and actual_digest != expected_digest:
                continue
        original = text
        existing_lines = [line.strip() for line in text.splitlines() if line.strip()]
        changed = False

        # Replace weak guidance before appending new lines.
        for rule in update.replace_rules:
            if rule.find in text and rule.replace not in text:
                text = text.replace(rule.find, rule.replace, 1)
                changed = True

        section = "## Learned Updates"
        if section not in text:
            if not text.endswith("\n"):
                text += "\n"
            text += f"\n{section}\n"

        for bullet in update.append_bullets:
            if any(_jaccard(bullet, line) >= 0.55 for line in existing_lines):
                continue
            evidence = ", ".join(str(step) for step in sorted(set(update.evidence_steps))[:4])
            line = f"- [{stamp}] {bullet} (evidence steps: {evidence})"
            if line in text:
                continue
            if not text.endswith("\n"):
                text += "\n"
            text += line + "\n"
            changed = True

        if changed and text != original:
            meta, span = _parse_frontmatter(text)
            if span is not None:
                raw_version = str(meta.get("version", "1")).strip()
                version = int(raw_version) if raw_version.isdigit() else 1
                meta["version"] = str(max(1, version) + 1)
                text = _render_frontmatter(meta) + text[span[1] :]
            backup = path.with_suffix(path.suffix + ".bak")
            if not backup.exists():
                backup.write_text(original, encoding="utf-8")
            path.write_text(text, encoding="utf-8")
            result["applied"] += 1
            result["updated_skill_refs"].append(update.skill_ref)

    if result["applied"] <= 0 and result["skipped_reason"] is None:
        result["skipped_reason"] = "no_applicable_changes"
    if result["applied"] > 0:
        build_skill_manifest(skills_root=skills_root, manifest_path=manifest_path)
    return result


def _update_to_dict(update: SkillUpdate) -> dict[str, Any]:
    return {
        "skill_ref": update.skill_ref,
        "skill_digest": update.skill_digest,
        "root_cause": update.root_cause,
        "evidence_steps": update.evidence_steps,
        "replace_rules": [{"find": rule.find, "replace": rule.replace} for rule in update.replace_rules],
        "append_bullets": update.append_bullets,
    }


def queue_skill_update_candidates(
    *,
    queue_path: Path,
    updates: list[SkillUpdate],
    confidence: float,
    session_id: int,
    task_id: str,
    required_skill_digests: dict[str, str] | None = None,
    allowed_skill_refs: set[str] | None = None,
    min_confidence: float = 0.7,
    max_skills: int = 2,
    evaluation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "attempted": bool(updates),
        "queued": 0,
        "confidence": confidence,
        "queued_skill_refs": [],
        "queue_path": str(queue_path),
        "skipped_reason": None,
    }
    if not updates:
        result["skipped_reason"] = "no_updates"
        return result
    if confidence < min_confidence:
        result["skipped_reason"] = f"low_confidence<{min_confidence}"
        return result

    if queue_path.exists():
        try:
            parsed = json.loads(queue_path.read_text(encoding="utf-8"))
            queue = parsed if isinstance(parsed, list) else []
        except Exception:
            queue = []
    else:
        queue = []

    payload_updates: list[dict[str, Any]] = []
    for update in updates[:max_skills]:
        if allowed_skill_refs is not None and update.skill_ref not in allowed_skill_refs:
            continue
        if required_skill_digests is not None:
            expected = required_skill_digests.get(update.skill_ref, "")
            if not expected or expected.lower() != update.skill_digest.lower():
                continue
        if not update.root_cause or not update.evidence_steps:
            continue
        payload_updates.append(_update_to_dict(update))
    if not payload_updates:
        result["skipped_reason"] = "no_updates_after_gates"
        return result

    now = datetime.now(timezone.utc)
    queue.append(
        {
            "id": f"{int(now.timestamp())}-{session_id}",
            "created_at": now.isoformat(),
            "session_id": session_id,
            "task_id": task_id,
            "confidence": confidence,
            "evaluation": evaluation or {},
            "updates": payload_updates,
        }
    )
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(json.dumps(queue, indent=2, ensure_ascii=True), encoding="utf-8")
    result["queued"] = len(payload_updates)
    result["queued_skill_refs"] = [row["skill_ref"] for row in payload_updates]
    return result


def _candidate_to_updates(candidate: dict[str, Any]) -> list[SkillUpdate]:
    updates_raw = candidate.get("updates", [])
    if not isinstance(updates_raw, list):
        return []
    updates: list[SkillUpdate] = []
    for item in updates_raw:
        if not isinstance(item, dict):
            continue
        skill_ref = item.get("skill_ref")
        digest = item.get("skill_digest")
        root_cause = item.get("root_cause")
        if not isinstance(skill_ref, str) or not isinstance(digest, str) or not isinstance(root_cause, str):
            continue
        steps_raw = item.get("evidence_steps", [])
        if not isinstance(steps_raw, list):
            continue
        steps = [int(step) for step in steps_raw if isinstance(step, int) and step > 0][:8]
        if not steps:
            continue
        replace_rules: list[ReplaceRule] = []
        replace_raw = item.get("replace_rules", [])
        if isinstance(replace_raw, list):
            for rule in replace_raw[:5]:
                if not isinstance(rule, dict):
                    continue
                find = rule.get("find")
                replace = rule.get("replace")
                if isinstance(find, str) and isinstance(replace, str):
                    find = " ".join(find.split())
                    replace = " ".join(replace.split())
                    if find and replace:
                        replace_rules.append(ReplaceRule(find=find, replace=replace))
        append_bullets: list[str] = []
        append_raw = item.get("append_bullets", [])
        if isinstance(append_raw, list):
            for bullet in append_raw[:5]:
                if not isinstance(bullet, str):
                    continue
                normalized = " ".join(bullet.split())
                if normalized:
                    append_bullets.append(normalized[:220])
        if not replace_rules and not append_bullets:
            continue
        updates.append(
            SkillUpdate(
                skill_ref=skill_ref.strip(),
                skill_digest=digest.strip().lower(),
                root_cause=" ".join(root_cause.split())[:400],
                evidence_steps=steps,
                replace_rules=replace_rules,
                append_bullets=append_bullets,
            )
        )
    return updates


def _collect_recent_scores(*, sessions_root: Path, task_id: str, max_sessions: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not sessions_root.exists():
        return rows
    session_dirs = sorted(
        (path for path in sessions_root.iterdir() if path.is_dir() and path.name.startswith("session-")),
        key=lambda path: int(path.name.split("-")[-1]) if path.name.split("-")[-1].isdigit() else 0,
    )
    for session_dir in session_dirs:
        metrics_path = session_dir / "metrics.json"
        if not metrics_path.exists():
            continue
        try:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(metrics, dict):
            continue
        if str(metrics.get("task_id", "")).strip() != task_id:
            continue
        try:
            score = float(metrics.get("eval_score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        rows.append(
            {
                "session_id": int(metrics.get("session_id", 0) or 0),
                "score": score,
                "passed": bool(metrics.get("eval_passed", False)),
            }
        )
    return rows[-max_sessions:]


def _scores_improving(rows: list[dict[str, Any]], *, min_runs: int, min_delta: float) -> bool:
    if len(rows) < min_runs:
        return False
    recent = rows[-min_runs:]
    scores = [float(row.get("score", 0.0)) for row in recent]
    return all(scores[idx] <= scores[idx + 1] for idx in range(len(scores) - 1)) and ((scores[-1] - scores[0]) >= min_delta)


def auto_promote_queued_candidates(
    *,
    entries: list[SkillManifestEntry],
    queue_path: Path,
    promoted_path: Path,
    sessions_root: Path,
    task_id: str,
    skills_root: Path,
    manifest_path: Path,
    min_runs: int = 3,
    min_delta: float = 0.2,
    max_sessions: int = 8,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "attempted": True,
        "applied": 0,
        "promoted_id": None,
        "reason": None,
        "gate_scores": [],
    }
    if not queue_path.exists():
        result["reason"] = "no_queue"
        return result
    try:
        parsed = json.loads(queue_path.read_text(encoding="utf-8"))
        queue = parsed if isinstance(parsed, list) else []
    except Exception:
        queue = []
    if not queue:
        result["reason"] = "empty_queue"
        return result

    score_rows = _collect_recent_scores(sessions_root=sessions_root, task_id=task_id, max_sessions=max_sessions)
    result["gate_scores"] = score_rows
    if len(score_rows) < min_runs:
        result["reason"] = "insufficient_runs_for_promotion"
        return result
    if not _scores_improving(score_rows, min_runs=min_runs, min_delta=min_delta):
        result["reason"] = "score_not_improving"
        return result

    candidates = [item for item in queue if isinstance(item, dict) and str(item.get("task_id", "")).strip() == task_id]
    if not candidates:
        result["reason"] = "no_task_candidates"
        return result
    candidates.sort(key=lambda item: (float(item.get("confidence", 0.0)), int(item.get("session_id", 0))), reverse=True)
    candidate = candidates[0]
    updates = _candidate_to_updates(candidate)
    if not updates:
        result["reason"] = "candidate_has_no_updates"
        return result

    required_digests = {update.skill_ref: update.skill_digest for update in updates}
    allowed_refs = {update.skill_ref for update in updates}
    apply_result = apply_skill_updates(
        entries=entries,
        updates=updates,
        confidence=float(candidate.get("confidence", 0.0)),
        skills_root=skills_root,
        manifest_path=manifest_path,
        required_skill_digests=required_digests,
        allowed_skill_refs=allowed_refs,
    )
    applied_count = int(apply_result.get("applied", 0))
    result["applied"] = applied_count
    result["reason"] = apply_result.get("skipped_reason")
    if applied_count <= 0:
        return result

    candidate_id = str(candidate.get("id", ""))
    result["promoted_id"] = candidate_id
    remaining = [item for item in queue if not (isinstance(item, dict) and str(item.get("id", "")) == candidate_id)]
    queue_path.write_text(json.dumps(remaining, indent=2, ensure_ascii=True), encoding="utf-8")

    if promoted_path.exists():
        try:
            parsed_promoted = json.loads(promoted_path.read_text(encoding="utf-8"))
            promoted_rows = parsed_promoted if isinstance(parsed_promoted, list) else []
        except Exception:
            promoted_rows = []
    else:
        promoted_rows = []
    promoted_rows.append(
        {
            "id": candidate_id,
            "promoted_at": datetime.now(timezone.utc).isoformat(),
            "candidate": candidate,
            "gate_scores": score_rows,
            "apply_result": apply_result,
        }
    )
    promoted_path.parent.mkdir(parents=True, exist_ok=True)
    promoted_path.write_text(json.dumps(promoted_rows, indent=2, ensure_ascii=True), encoding="utf-8")
    return result
