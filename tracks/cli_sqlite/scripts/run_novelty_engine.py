#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tracks.cli_sqlite.novelty_engine import build_snapshot, render_snapshot_text, snapshot_to_dict


TRACK_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SESSIONS_ROOT = TRACK_ROOT / "sessions"


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize weak spots and recommend the next novelty tasks.")
    ap.add_argument(
        "--sessions-root",
        default=str(DEFAULT_SESSIONS_ROOT),
        help="Root containing session-*/metrics.json artifacts.",
    )
    ap.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format. text is easier to scan; json is easier to script.",
    )
    ap.add_argument(
        "--write",
        default="",
        help="Optional path to write the rendered snapshot. JSON when --format=json, plain text otherwise.",
    )
    args = ap.parse_args()

    snapshot = build_snapshot(sessions_root=Path(args.sessions_root))
    rendered = (
        json.dumps(snapshot_to_dict(snapshot), indent=2, sort_keys=True)
        if args.format == "json"
        else render_snapshot_text(snapshot)
    )
    print(rendered)

    if args.write:
        target = Path(args.write)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered + ("\n" if not rendered.endswith("\n") else ""), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
