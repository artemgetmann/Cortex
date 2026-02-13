from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skill_routing import SkillManifestEntry, build_skill_manifest


def _tokenize(text: str) -> set[str]:
    return {t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split() if t}


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


def _parse_frontmatter(text: str) -> tuple[dict[str, str], tuple[int, int] | None]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, None
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, None
    meta: dict[str, str] = {}
    for raw in lines[1:end_idx]:
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"').strip("'")
    span_end = sum(len(ln) for ln in lines[: end_idx + 1])
    return meta, (0, span_end)


def _render_frontmatter(meta: dict[str, str]) -> str:
    ordered = ["name", "description", "version"]
    out: list[str] = ["---\n"]
    for key in ordered:
        if key in meta and str(meta[key]).strip():
            out.append(f"{key}: {meta[key]}\n")
    for key in sorted(meta.keys()):
        if key in ordered:
            continue
        value = str(meta[key]).strip()
        if not value:
            continue
        out.append(f"{key}: {value}\n")
    out.append("---\n")
    return "".join(out)


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
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


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
        skill_digest_value = item.get("skill_digest", "")
        root_cause = item.get("root_cause", "")
        evidence_steps = item.get("evidence_steps", [])
        replace_rules_raw = item.get("replace_rules", [])
        append_bullets = item.get("append_bullets")
        if not isinstance(skill_ref, str):
            continue
        if not isinstance(skill_digest_value, str):
            continue
        if not isinstance(root_cause, str):
            continue
        if not isinstance(evidence_steps, list):
            continue
        clean_steps: list[int] = []
        for s in evidence_steps:
            if isinstance(s, int) and s > 0:
                clean_steps.append(s)
        clean_steps = clean_steps[:8]
        if not isinstance(replace_rules_raw, list):
            continue
        replace_rules: list[ReplaceRule] = []
        for rr in replace_rules_raw[:5]:
            if not isinstance(rr, dict):
                continue
            find = rr.get("find")
            replace = rr.get("replace")
            if not isinstance(find, str) or not isinstance(replace, str):
                continue
            find = " ".join(find.strip().split())
            replace = " ".join(replace.strip().split())
            if not find or not replace:
                continue
            replace_rules.append(ReplaceRule(find=find, replace=replace))
        if not isinstance(append_bullets, list):
            continue
        cleaned: list[str] = []
        for bullet in append_bullets:
            if not isinstance(bullet, str):
                continue
            b = " ".join(bullet.strip().split())
            if not b:
                continue
            if len(b) > 220:
                b = b[:217] + "..."
            cleaned.append(b)
        if cleaned or replace_rules:
            updates.append(
                SkillUpdate(
                    skill_ref=skill_ref.strip(),
                    skill_digest=skill_digest_value.strip().lower(),
                    root_cause=" ".join(root_cause.strip().split())[:400],
                    evidence_steps=clean_steps,
                    replace_rules=replace_rules,
                    append_bullets=cleaned[:5],
                )
            )
    return updates, confidence


def apply_skill_updates(
    *,
    entries: list[SkillManifestEntry],
    updates: list[SkillUpdate],
    confidence: float,
    min_confidence: float = 0.7,
    max_skills: int = 2,
    valid_steps: set[int] | None = None,
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

    by_ref = {e.skill_ref: e for e in entries}
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for upd in updates[:max_skills]:
        entry = by_ref.get(upd.skill_ref)
        if entry is None:
            continue
        if allowed_skill_refs is not None and upd.skill_ref not in allowed_skill_refs:
            continue
        if required_skill_digests is not None:
            expected = required_skill_digests.get(upd.skill_ref, "")
            if not expected:
                continue
            if upd.skill_digest != expected.lower():
                continue
        if not upd.root_cause:
            continue
        if not upd.evidence_steps:
            continue
        if valid_steps is not None and not any(step in valid_steps for step in upd.evidence_steps):
            continue
        p = Path(entry.path)
        if not p.exists():
            continue

        text = p.read_text(encoding="utf-8")
        if required_skill_digests is not None:
            actual = skill_digest(text)
            expected = required_skill_digests.get(upd.skill_ref, "")
            if expected and actual.lower() != expected.lower():
                continue
        original_text = text
        existing_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        changed = False

        # First, let model patch existing rules when it pinpoints an insufficient rule.
        for rr in upd.replace_rules:
            if rr.find in text and rr.replace not in text:
                text = text.replace(rr.find, rr.replace, 1)
                changed = True

        section = "## Learned Updates"
        if section not in text:
            if not text.endswith("\n"):
                text += "\n"
            text += f"\n{section}\n"

        for bullet in upd.append_bullets:
            # Reject near-duplicate generic advice.
            if any(_jaccard(bullet, existing) >= 0.55 for existing in existing_lines):
                continue
            evidence_suffix = ", ".join(str(s) for s in sorted(set(upd.evidence_steps))[:4])
            bullet_line = f"{bullet} (evidence steps: {evidence_suffix})"
            line = f"- [{stamp}] {bullet}"
            if line in text or bullet_line in text:
                continue
            if not text.endswith("\n"):
                text += "\n"
            text += f"- [{stamp}] {bullet_line}\n"
            changed = True

        if changed and text != original_text:
            meta, span = _parse_frontmatter(text)
            if span is not None:
                current_version = 1
                raw = str(meta.get("version", "")).strip()
                if raw.isdigit():
                    current_version = max(1, int(raw))
                meta["version"] = str(current_version + 1)
                fm = _render_frontmatter(meta)
                text = fm + text[span[1] :]
            backup = p.with_suffix(p.suffix + ".bak")
            if not backup.exists():
                backup.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
            p.write_text(text, encoding="utf-8")
            result["applied"] += 1
            result["updated_skill_refs"].append(upd.skill_ref)

    if result["applied"] == 0 and result["skipped_reason"] is None:
        result["skipped_reason"] = "no_applicable_changes"

    # Keep manifest aligned if any skill changed.
    if result["applied"] > 0:
        build_skill_manifest()

    return result


def _update_to_dict(upd: SkillUpdate) -> dict[str, Any]:
    return {
        "skill_ref": upd.skill_ref,
        "skill_digest": upd.skill_digest,
        "root_cause": upd.root_cause,
        "evidence_steps": upd.evidence_steps,
        "replace_rules": [{"find": rr.find, "replace": rr.replace} for rr in upd.replace_rules],
        "append_bullets": upd.append_bullets,
    }


def queue_skill_update_candidates(
    *,
    updates: list[SkillUpdate],
    confidence: float,
    session_id: int,
    required_skill_digests: dict[str, str] | None = None,
    allowed_skill_refs: set[str] | None = None,
    min_confidence: float = 0.7,
    max_skills: int = 2,
    evaluation: dict[str, Any] | None = None,
    queue_path: Path = Path("learning/pending_skill_patches.json"),
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "attempted": bool(updates),
        "queued": 0,
        "confidence": confidence,
        "queue_path": str(queue_path),
        "queued_skill_refs": [],
        "skipped_reason": None,
    }

    if not updates:
        result["skipped_reason"] = "no_updates"
        return result
    if confidence < min_confidence:
        result["skipped_reason"] = f"low_confidence<{min_confidence}"
        return result

    queue_path.parent.mkdir(parents=True, exist_ok=True)
    if queue_path.exists():
        try:
            raw = json.loads(queue_path.read_text(encoding="utf-8"))
            queue = raw if isinstance(raw, list) else []
        except Exception:
            queue = []
    else:
        queue = []

    queued_updates: list[dict[str, Any]] = []
    for upd in updates[:max_skills]:
        if allowed_skill_refs is not None and upd.skill_ref not in allowed_skill_refs:
            continue
        if required_skill_digests is not None:
            expected = required_skill_digests.get(upd.skill_ref, "")
            if not expected:
                continue
            if upd.skill_digest != expected.lower():
                continue
        if not upd.root_cause:
            continue
        if not upd.evidence_steps:
            continue
        queued_updates.append(_update_to_dict(upd))

    if not queued_updates:
        result["skipped_reason"] = "no_updates_after_gates"
        return result

    now = datetime.now(timezone.utc)
    queue.append(
        {
            "id": f"{int(now.timestamp())}-{session_id}",
            "created_at": now.isoformat(),
            "session_id": session_id,
            "confidence": confidence,
            "evaluation": evaluation or {},
            "updates": queued_updates,
        }
    )
    queue_path.write_text(json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8")
    result["queued"] = len(queued_updates)
    result["queued_skill_refs"] = [u["skill_ref"] for u in queued_updates]
    return result


def _candidate_update_to_model(item: dict[str, Any]) -> SkillUpdate | None:
    if not isinstance(item, dict):
        return None
    skill_ref = item.get("skill_ref")
    digest = item.get("skill_digest")
    root_cause = item.get("root_cause")
    evidence_steps = item.get("evidence_steps")
    if not isinstance(skill_ref, str) or not isinstance(digest, str) or not isinstance(root_cause, str):
        return None
    if not isinstance(evidence_steps, list):
        return None
    clean_steps = [int(s) for s in evidence_steps if isinstance(s, int) and s > 0][:8]
    if not clean_steps:
        return None

    replace_rules_raw = item.get("replace_rules", [])
    replace_rules: list[ReplaceRule] = []
    if isinstance(replace_rules_raw, list):
        for rr in replace_rules_raw[:5]:
            if not isinstance(rr, dict):
                continue
            find = rr.get("find")
            replace = rr.get("replace")
            if isinstance(find, str) and isinstance(replace, str):
                find = " ".join(find.split())
                replace = " ".join(replace.split())
                if find and replace:
                    replace_rules.append(ReplaceRule(find=find, replace=replace))

    append_raw = item.get("append_bullets", [])
    append_bullets: list[str] = []
    if isinstance(append_raw, list):
        for bullet in append_raw[:5]:
            if not isinstance(bullet, str):
                continue
            normalized = " ".join(bullet.split())
            if normalized:
                append_bullets.append(normalized)
    if not append_bullets and not replace_rules:
        return None

    return SkillUpdate(
        skill_ref=skill_ref.strip(),
        skill_digest=digest.strip().lower(),
        root_cause=" ".join(root_cause.split())[:400],
        evidence_steps=clean_steps,
        replace_rules=replace_rules,
        append_bullets=append_bullets,
    )


def _read_session_events(jsonl_path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not jsonl_path.exists():
        return events
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            events.append(row)
    return events


def _collect_recent_drum_scores(
    *,
    sessions_root: Path,
    max_sessions: int,
) -> list[dict[str, Any]]:
    # Local import avoids widening module dependencies for non-learning paths.
    from run_eval import evaluate_drum_run

    rows: list[dict[str, Any]] = []
    if not sessions_root.exists():
        return rows
    dirs = sorted(
        (
            p
            for p in sessions_root.iterdir()
            if p.is_dir() and p.name.startswith("session-") and p.name[8:].isdigit()
        ),
        key=lambda p: int(p.name[8:]),
    )
    for d in dirs:
        session_id = int(d.name[8:])
        events = _read_session_events(d / "events.jsonl")
        if not events:
            continue
        task = "Create a 4-on-the-floor kick drum pattern in FL Studio"
        metrics_path = d / "metrics.json"
        if metrics_path.exists():
            try:
                metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
                if isinstance(metrics, dict):
                    mt = metrics.get("task")
                    if isinstance(mt, str) and mt.strip():
                        task = mt
            except Exception:
                pass
        ev = evaluate_drum_run(task, events)
        if not ev.applicable:
            continue
        rows.append({"session_id": session_id, "score": ev.score, "passed": ev.passed})
    return rows[-max_sessions:]


def _scores_improving(rows: list[dict[str, Any]], *, min_runs: int, min_delta: float) -> bool:
    if len(rows) < min_runs:
        return False
    recent = rows[-min_runs:]
    scores = [float(r.get("score", 0.0)) for r in recent]
    non_decreasing = all(scores[i] <= scores[i + 1] for i in range(len(scores) - 1))
    delta_ok = (scores[-1] - scores[0]) >= min_delta
    return non_decreasing and delta_ok


def auto_promote_queued_candidates(
    *,
    entries: list[SkillManifestEntry],
    queue_path: Path = Path("learning/pending_skill_patches.json"),
    promoted_path: Path = Path("learning/promoted_skill_patches.json"),
    sessions_root: Path = Path("sessions"),
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
        raw = json.loads(queue_path.read_text(encoding="utf-8"))
        queue = raw if isinstance(raw, list) else []
    except Exception:
        queue = []
    if not queue:
        result["reason"] = "empty_queue"
        return result

    score_rows = _collect_recent_drum_scores(sessions_root=sessions_root, max_sessions=max_sessions)
    result["gate_scores"] = score_rows
    if len(score_rows) < min_runs:
        result["reason"] = "insufficient_runs_for_promotion"
        return result
    if not _scores_improving(score_rows, min_runs=min_runs, min_delta=min_delta):
        result["reason"] = "score_not_improving"
        return result

    ranked = sorted(
        (c for c in queue if isinstance(c, dict)),
        key=lambda c: (float(c.get("confidence", 0.0)), int(c.get("session_id", 0))),
        reverse=True,
    )
    if not ranked:
        result["reason"] = "no_valid_candidates"
        return result
    candidate = ranked[0]
    updates_raw = candidate.get("updates", [])
    updates: list[SkillUpdate] = []
    if isinstance(updates_raw, list):
        for item in updates_raw:
            upd = _candidate_update_to_model(item)
            if upd is not None:
                updates.append(upd)
    if not updates:
        result["reason"] = "candidate_has_no_updates"
        return result

    required_digests = {u.skill_ref: u.skill_digest for u in updates if u.skill_ref and u.skill_digest}
    allowed_refs = {u.skill_ref for u in updates if u.skill_ref}
    applied = apply_skill_updates(
        entries=entries,
        updates=updates,
        confidence=float(candidate.get("confidence", 0.0)),
        min_confidence=0.7,
        required_skill_digests=required_digests,
        allowed_skill_refs=allowed_refs,
    )
    result["applied"] = int(applied.get("applied", 0))
    result["reason"] = applied.get("skipped_reason")
    if result["applied"] <= 0:
        return result

    cid = str(candidate.get("id", ""))
    result["promoted_id"] = cid

    # Remove promoted candidate from queue and persist.
    remaining = [c for c in queue if not (isinstance(c, dict) and str(c.get("id", "")) == cid)]
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(json.dumps(remaining, indent=2, ensure_ascii=False), encoding="utf-8")

    # Append promotion audit trail.
    promoted_path.parent.mkdir(parents=True, exist_ok=True)
    if promoted_path.exists():
        try:
            old = json.loads(promoted_path.read_text(encoding="utf-8"))
            promoted_rows = old if isinstance(old, list) else []
        except Exception:
            promoted_rows = []
    else:
        promoted_rows = []
    promoted_rows.append(
        {
            "id": cid,
            "promoted_at": datetime.now(timezone.utc).isoformat(),
            "candidate": candidate,
            "gate_scores": score_rows,
            "apply_result": applied,
        }
    )
    promoted_path.write_text(json.dumps(promoted_rows, indent=2, ensure_ascii=False), encoding="utf-8")
    return result
