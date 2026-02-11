from __future__ import annotations

"""
Between-session consolidation:
- Reads sessions/session-*/events.jsonl
- Produces sessions/lessons/top-20.md (and later can propose skill updates)

Stub for now: wire it after the agent loop is stable.
"""

import argparse
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="Input events.jsonl")
    ap.add_argument("--out", dest="out", required=True, help="Output markdown path")
    args = ap.parse_args()

    inp = Path(args.inp)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Placeholder: just record that consolidation isn't implemented yet.
    out.write_text(
        "# Lessons (placeholder)\n\nConsolidation not implemented yet.\n",
        encoding="utf-8",
    )
    print(f"Wrote {out}")
    print(f"Input was {inp} (not processed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

