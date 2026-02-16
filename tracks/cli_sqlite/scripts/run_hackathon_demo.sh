#!/usr/bin/env bash
set -euo pipefail

# Hackathon demo runner (prepared script, not auto-executed by Codex).
# Purpose:
# - Run 3 sequential waves of the mixed benchmark using the same memory store
# - Capture JSON artifacts for each wave
# - Keep flags stable for reproducibility in recorded demos
#
# Usage:
#   bash tracks/cli_sqlite/scripts/run_hackathon_demo.sh
#   START_SESSION=56001 MAX_STEPS=5 bash tracks/cli_sqlite/scripts/run_hackathon_demo.sh
#
# Notes:
# - Wave 1 clears lessons to start from cold memory.
# - Waves 2 and 3 reuse memory from prior waves.
# - This script does not run automatically; it is for manual demo execution.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "${ROOT_DIR}"

START_SESSION="${START_SESSION:-56001}"
MAX_STEPS="${MAX_STEPS:-5}"
LEARNING_MODE="${LEARNING_MODE:-strict}"
POSTTASK_MODE="${POSTTASK_MODE:-candidate}"
OUTPUT_DIR="${OUTPUT_DIR:-/tmp}"

# Each mixed benchmark wave uses 5 sessions with defaults below.
WAVE_SIZE=5
WAVE1_START="${START_SESSION}"
WAVE2_START="$((START_SESSION + WAVE_SIZE))"
WAVE3_START="$((START_SESSION + (2 * WAVE_SIZE)))"

WAVE1_JSON="${OUTPUT_DIR}/memory_mixed_wave1_${WAVE1_START}.json"
WAVE2_JSON="${OUTPUT_DIR}/memory_mixed_wave2_${WAVE2_START}.json"
WAVE3_JSON="${OUTPUT_DIR}/memory_mixed_wave3_${WAVE3_START}.json"

echo "== Memory V2 Hackathon Demo =="
echo "root=${ROOT_DIR}"
echo "start_session=${START_SESSION} max_steps=${MAX_STEPS} learning_mode=${LEARNING_MODE}"
echo "outputs:"
echo "  ${WAVE1_JSON}"
echo "  ${WAVE2_JSON}"
echo "  ${WAVE3_JSON}"
echo

echo "== Wave 1 (cold start, clear lessons) =="
python3 tracks/cli_sqlite/scripts/run_mixed_benchmark.py \
  --grid-task-id aggregate_report \
  --fluxtool-task-id aggregate_report_holdout \
  --shell-task-id shell_excel_build_report \
  --sqlite-task-id import_aggregate \
  --grid-runs 1 \
  --fluxtool-runs 1 \
  --shell-runs 1 \
  --sqlite-runs 1 \
  --retention-runs 1 \
  --start-session "${WAVE1_START}" \
  --max-steps "${MAX_STEPS}" \
  --learning-mode "${LEARNING_MODE}" \
  --posttask-mode "${POSTTASK_MODE}" \
  --bootstrap \
  --mixed-errors \
  --cryptic-errors \
  --clear-lessons \
  --output-json "${WAVE1_JSON}"

echo
echo "== Wave 2 (memory reused) =="
python3 tracks/cli_sqlite/scripts/run_mixed_benchmark.py \
  --grid-task-id aggregate_report \
  --fluxtool-task-id aggregate_report_holdout \
  --shell-task-id shell_excel_build_report \
  --sqlite-task-id import_aggregate \
  --grid-runs 1 \
  --fluxtool-runs 1 \
  --shell-runs 1 \
  --sqlite-runs 1 \
  --retention-runs 1 \
  --start-session "${WAVE2_START}" \
  --max-steps "${MAX_STEPS}" \
  --learning-mode "${LEARNING_MODE}" \
  --posttask-mode "${POSTTASK_MODE}" \
  --bootstrap \
  --mixed-errors \
  --cryptic-errors \
  --output-json "${WAVE2_JSON}"

echo
echo "== Wave 3 (memory reused) =="
python3 tracks/cli_sqlite/scripts/run_mixed_benchmark.py \
  --grid-task-id aggregate_report \
  --fluxtool-task-id aggregate_report_holdout \
  --shell-task-id shell_excel_build_report \
  --sqlite-task-id import_aggregate \
  --grid-runs 1 \
  --fluxtool-runs 1 \
  --shell-runs 1 \
  --sqlite-runs 1 \
  --retention-runs 1 \
  --start-session "${WAVE3_START}" \
  --max-steps "${MAX_STEPS}" \
  --learning-mode "${LEARNING_MODE}" \
  --posttask-mode "${POSTTASK_MODE}" \
  --bootstrap \
  --mixed-errors \
  --cryptic-errors \
  --output-json "${WAVE3_JSON}"

echo
echo "== Suggested timeline commands for demo narration =="
echo "python3 tracks/cli_sqlite/scripts/memory_timeline_demo.py --session $((WAVE1_START + 1)) --show-ok-steps --show-all-tools --show-tool-output --show-lessons 6"
echo "python3 tracks/cli_sqlite/scripts/memory_timeline_demo.py --session $((WAVE2_START + 1)) --show-ok-steps --show-all-tools --show-tool-output --show-lessons 6"
echo "python3 tracks/cli_sqlite/scripts/memory_timeline_demo.py --session $((WAVE3_START + 1)) --show-ok-steps --show-all-tools --show-tool-output --show-lessons 6"
echo
echo "Done."
