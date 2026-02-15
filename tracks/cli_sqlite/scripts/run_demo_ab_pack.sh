#!/usr/bin/env bash
set -euo pipefail

# Run a reproducible A/B benchmark pack across both holdout-style domains and
# write machine-readable + presentation-ready outputs into a timestamped folder.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT_DIR"

SESSIONS_PER_ARM="${SESSIONS_PER_ARM:-10}"
MAX_STEPS="${MAX_STEPS:-8}"
LEARNING_MODE="${LEARNING_MODE:-strict}"
START_GRID="${START_GRID:-34000}"
START_FLUX="${START_FLUX:-35000}"

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_DIR="tracks/cli_sqlite/artifacts/ab/${STAMP}"
mkdir -p "$OUT_DIR"

echo "== A/B demo pack =="
echo "output_dir=$OUT_DIR"
echo "sessions_per_arm=$SESSIONS_PER_ARM max_steps=$MAX_STEPS learning_mode=$LEARNING_MODE"
echo

python3 tracks/cli_sqlite/scripts/run_architecture_ab.py \
  --domain gridtool \
  --task-id aggregate_report \
  --learning-mode "$LEARNING_MODE" \
  --sessions "$SESSIONS_PER_ARM" \
  --start-session "$START_GRID" \
  --max-steps "$MAX_STEPS" \
  --bootstrap \
  --mixed-errors \
  --clear-lessons-between-arms \
  --output-json "$OUT_DIR/gridtool_ab.json" \
  --output-md "$OUT_DIR/gridtool_ab.md"

echo

python3 tracks/cli_sqlite/scripts/run_architecture_ab.py \
  --domain fluxtool \
  --task-id aggregate_report_holdout \
  --learning-mode "$LEARNING_MODE" \
  --sessions "$SESSIONS_PER_ARM" \
  --start-session "$START_FLUX" \
  --max-steps "$MAX_STEPS" \
  --bootstrap \
  --mixed-errors \
  --clear-lessons-between-arms \
  --output-json "$OUT_DIR/fluxtool_ab.json" \
  --output-md "$OUT_DIR/fluxtool_ab.md"

echo
echo "== Topline =="
python3 - <<'PY' "$OUT_DIR/gridtool_ab.json" "$OUT_DIR/fluxtool_ab.json"
import json
import sys
from pathlib import Path

for path_str in sys.argv[1:]:
    payload = json.loads(Path(path_str).read_text(encoding="utf-8"))
    domain = payload["config"]["domain"]
    full = payload["arms"]["full"]
    simp = payload["arms"]["simplified"]
    delta = payload["deltas"]
    print(f"{domain}: full_pass={full['pass_rate']:.2%} simplified_pass={simp['pass_rate']:.2%} delta={delta['pass_rate']:+.2%}")
    print(
        f"  full_score={full['mean_score']:.3f} simplified_score={simp['mean_score']:.3f} "
        f"steps_delta={delta['mean_steps']:+.2f} err_delta={delta['mean_tool_errors']:+.2f}"
    )
PY

echo
echo "Artifacts ready:"
echo "  $OUT_DIR/gridtool_ab.json"
echo "  $OUT_DIR/gridtool_ab.md"
echo "  $OUT_DIR/fluxtool_ab.json"
echo "  $OUT_DIR/fluxtool_ab.md"
