from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


ENV_RUNTIME_LANE = "CORTEX_RUNTIME_LANE"
RUNTIME_ROOT_DIRNAME = "runtime"
DEFAULT_RUNTIME_LANE = ""

_LANE_SANITIZE_RE = re.compile(r"[^a-z0-9_-]+")


@dataclass(frozen=True)
class RuntimePaths:
    """Resolved storage roots for one isolated runtime lane.

    A lane is a lightweight namespace for session/lesson artifacts
    (example: benchmark default lane vs telegram lane). Isolating lanes keeps
    live bot memory from contaminating benchmark evidence.
    """

    lane: str
    sessions_root: Path
    learning_root: Path
    lessons_path: Path
    lessons_v2_path: Path
    memory_events_path: Path
    queue_path: Path
    promoted_path: Path
    escalation_state_path: Path


def _normalize_lane(raw: str | None) -> str:
    token = str(raw or "").strip().lower()
    if not token:
        return ""
    # Keep lane names filesystem-safe and deterministic.
    cleaned = _LANE_SANITIZE_RE.sub("-", token).strip("-")
    return cleaned


def resolve_runtime_lane(explicit_lane: str | None = None) -> str:
    """Resolve runtime lane from explicit input first, then environment."""

    if explicit_lane is not None:
        return _normalize_lane(explicit_lane)
    return _normalize_lane(os.getenv(ENV_RUNTIME_LANE, DEFAULT_RUNTIME_LANE))


def resolve_runtime_paths(*, track_root: Path, lane: str | None = None) -> RuntimePaths:
    """Compute lane-aware paths while preserving legacy defaults.

    Legacy behavior is unchanged when lane is empty:
      sessions -> tracks/cli_sqlite/sessions
      learning -> tracks/cli_sqlite/learning
    """

    resolved_lane = resolve_runtime_lane(lane)
    if resolved_lane:
        base_root = track_root / RUNTIME_ROOT_DIRNAME / resolved_lane
    else:
        base_root = track_root

    sessions_root = base_root / "sessions"
    learning_root = base_root / "learning"
    return RuntimePaths(
        lane=resolved_lane,
        sessions_root=sessions_root,
        learning_root=learning_root,
        lessons_path=learning_root / "lessons.jsonl",
        lessons_v2_path=learning_root / "lessons_v2.jsonl",
        memory_events_path=learning_root / "memory_events.jsonl",
        queue_path=learning_root / "pending_skill_patches.json",
        promoted_path=learning_root / "promoted_skill_patches.json",
        escalation_state_path=learning_root / "critic_escalation_state.json",
    )


__all__ = [
    "DEFAULT_RUNTIME_LANE",
    "ENV_RUNTIME_LANE",
    "RuntimePaths",
    "resolve_runtime_lane",
    "resolve_runtime_paths",
]
