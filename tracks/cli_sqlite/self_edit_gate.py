from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tracks.cli_sqlite.self_improve_cli import SkillUpdate, skill_digest
from tracks.cli_sqlite.skill_routing_cli import SkillManifestEntry

SELF_EDIT_TARGETS: tuple[tuple[str, str, str, str], ...] = (
    (
        "orchestration/agent_cli",
        "agent_cli.py",
        "agent-cli-orchestrator",
        "Primary CLI runtime orchestration loop.",
    ),
    (
        "orchestration/run_cli_agent_script",
        "scripts/run_cli_agent.py",
        "run-cli-agent-entrypoint",
        "CLI entrypoint for launching task sessions.",
    ),
    (
        "orchestration/run_observability",
        "run_observability.py",
        "run-observability",
        "Run lifecycle and ledger observability helpers.",
    ),
    (
        "orchestration/run_learning_curve_script",
        "scripts/run_learning_curve.py",
        "run-learning-curve-entrypoint",
        "Sequential learning-curve benchmark runner.",
    ),
)


def _empty_rejection_counts() -> dict[str, int]:
    return {
        "required_digest_mismatch": 0,
        "replace_miss": 0,
        "no_replace_rules": 0,
        "disallowed_ref": 0,
    }


def _bump_rejection_count(counts: dict[str, int], reason: str) -> None:
    key = str(reason or "").strip()
    if not key:
        return
    counts[key] = int(counts.get(key, 0)) + 1


def _format_last_updated(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def self_edit_allowed_refs() -> set[str]:
    return {row[0] for row in SELF_EDIT_TARGETS}


def build_self_edit_manifest_entries(*, track_root: Path) -> list[SkillManifestEntry]:
    entries: list[SkillManifestEntry] = []
    root = Path(track_root)
    for skill_ref, relative_path, title, description in SELF_EDIT_TARGETS:
        path = root / relative_path
        if not path.exists() or not path.is_file():
            continue
        entries.append(
            SkillManifestEntry(
                skill_ref=skill_ref,
                title=title,
                description=description,
                path=str(path.resolve()),
                version=1,
                last_updated=_format_last_updated(path),
                confidence=0.7,
            )
        )
    return entries


def default_self_edit_check_commands() -> list[list[str]]:
    python_bin = sys.executable or "python3"
    return [
        [python_bin, "-m", "pytest", "tracks/cli_sqlite/tests", "-q"],
        [python_bin, "tracks/cli_sqlite/scripts/run_cli_agent.py", "--help"],
        [python_bin, "tracks/cli_sqlite/scripts/run_learning_curve.py", "--help"],
    ]


def _clip_text(text: str, *, max_chars: int = 1200) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _run_verification_commands(
    *,
    track_root: Path,
    commands: list[list[str]],
) -> tuple[bool, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for cmd in commands:
        proc = subprocess.run(
            cmd,
            cwd=str(track_root),
            capture_output=True,
            text=True,
            check=False,
        )
        row = {
            "command": list(cmd),
            "exit_code": int(proc.returncode),
            "stdout": _clip_text(str(proc.stdout or "").strip(), max_chars=900),
            "stderr": _clip_text(str(proc.stderr or "").strip(), max_chars=900),
        }
        rows.append(row)
        if proc.returncode != 0:
            return False, rows
    return True, rows


def apply_guarded_self_edit_updates(
    *,
    entries: list[SkillManifestEntry],
    updates: list[SkillUpdate],
    confidence: float,
    track_root: Path,
    min_confidence: float = 0.7,
    max_skills: int = 2,
    required_skill_digests: dict[str, str] | None = None,
    allowed_skill_refs: set[str] | None = None,
    check_commands: list[list[str]] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "attempted": bool(updates),
        "proposed": int(len(updates)),
        "applied": 0,
        "updated_skill_refs": [],
        "confidence": float(confidence),
        "skipped_reason": None,
        "rolled_back": False,
        "verification": [],
        "rejection_counts": _empty_rejection_counts(),
    }
    if not updates:
        result["skipped_reason"] = "no_updates"
        return result
    if float(confidence) < float(min_confidence):
        result["skipped_reason"] = f"low_confidence<{float(min_confidence):.2f}"
        return result

    by_ref = {entry.skill_ref: entry for entry in entries}
    original_by_path: dict[Path, str] = {}

    for update in updates[: max(1, int(max_skills))]:
        ref = str(update.skill_ref or "").strip()
        if not ref:
            continue
        if allowed_skill_refs is not None and ref not in allowed_skill_refs:
            _bump_rejection_count(result["rejection_counts"], "disallowed_ref")
            continue
        entry = by_ref.get(ref)
        if entry is None:
            _bump_rejection_count(result["rejection_counts"], "disallowed_ref")
            continue

        path = Path(entry.path)
        if not path.exists() or not path.is_file():
            continue
        original_text = path.read_text(encoding="utf-8")
        if required_skill_digests is not None:
            expected = str(required_skill_digests.get(ref, "")).strip().lower()
            actual = skill_digest(original_text).lower()
            if not expected or expected != actual:
                _bump_rejection_count(result["rejection_counts"], "required_digest_mismatch")
                continue

        if not update.replace_rules:
            _bump_rejection_count(result["rejection_counts"], "no_replace_rules")
            continue

        updated_text = original_text
        changed = False
        for rule in update.replace_rules[:5]:
            if rule.find in updated_text and rule.replace not in updated_text:
                updated_text = updated_text.replace(rule.find, rule.replace, 1)
                changed = True
            elif rule.find not in updated_text:
                _bump_rejection_count(result["rejection_counts"], "replace_miss")
        if not changed or updated_text == original_text:
            continue

        if path not in original_by_path:
            original_by_path[path] = original_text
        path.write_text(updated_text, encoding="utf-8")
        result["applied"] = int(result["applied"]) + 1
        result["updated_skill_refs"].append(ref)

    if int(result["applied"]) <= 0:
        result["skipped_reason"] = "no_applicable_changes"
        return result

    commands = check_commands if check_commands is not None else default_self_edit_check_commands()
    checks_ok, check_rows = _run_verification_commands(
        track_root=Path(track_root),
        commands=commands,
    )
    result["verification"] = check_rows
    if checks_ok:
        return result

    for path, original_text in original_by_path.items():
        path.write_text(original_text, encoding="utf-8")
    result["rolled_back"] = True
    result["skipped_reason"] = "verification_failed"
    result["applied"] = 0
    result["updated_skill_refs"] = []
    return result
