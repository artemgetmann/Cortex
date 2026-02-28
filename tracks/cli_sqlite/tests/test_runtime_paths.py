from __future__ import annotations

from pathlib import Path

from tracks.cli_sqlite.runtime_paths import resolve_runtime_paths


def test_resolve_runtime_paths_default_lane_preserves_legacy_roots() -> None:
    track_root = Path("/tmp/cortex-track")
    resolved = resolve_runtime_paths(track_root=track_root, lane="")
    assert resolved.lane == ""
    assert resolved.sessions_root == track_root / "sessions"
    assert resolved.learning_root == track_root / "learning"
    assert resolved.lessons_v2_path == track_root / "learning" / "lessons_v2.jsonl"


def test_resolve_runtime_paths_named_lane_uses_runtime_subtree() -> None:
    track_root = Path("/tmp/cortex-track")
    resolved = resolve_runtime_paths(track_root=track_root, lane="telegram")
    assert resolved.lane == "telegram"
    assert resolved.sessions_root == track_root / "runtime" / "telegram" / "sessions"
    assert resolved.learning_root == track_root / "runtime" / "telegram" / "learning"
    assert resolved.lessons_path == track_root / "runtime" / "telegram" / "learning" / "lessons.jsonl"
