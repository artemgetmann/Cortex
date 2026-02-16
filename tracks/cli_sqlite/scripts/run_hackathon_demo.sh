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
AUTO_TIMELINE="${AUTO_TIMELINE:-1}"
AUTO_TOKEN_REPORT="${AUTO_TOKEN_REPORT:-1}"
TIMELINE_SHOW_LESSONS="${TIMELINE_SHOW_LESSONS:-6}"
TOKEN_REPORT_JSON="${OUTPUT_DIR}/memory_mixed_tokens_${START_SESSION}.json"

# Each mixed benchmark wave uses 5 sessions with defaults below.
WAVE_SIZE=5
WAVE1_START="${START_SESSION}"
WAVE2_START="$((START_SESSION + WAVE_SIZE))"
WAVE3_START="$((START_SESSION + (2 * WAVE_SIZE)))"

WAVE1_JSON="${OUTPUT_DIR}/memory_mixed_wave1_${WAVE1_START}.json"
WAVE2_JSON="${OUTPUT_DIR}/memory_mixed_wave2_${WAVE2_START}.json"
WAVE3_JSON="${OUTPUT_DIR}/memory_mixed_wave3_${WAVE3_START}.json"
WAVE1_TIMELINE="${OUTPUT_DIR}/memory_timeline_wave1_${WAVE1_START}.txt"
WAVE2_TIMELINE="${OUTPUT_DIR}/memory_timeline_wave2_${WAVE2_START}.txt"
WAVE3_TIMELINE="${OUTPUT_DIR}/memory_timeline_wave3_${WAVE3_START}.txt"

pick_timeline_session() {
  local wave_json="$1"
  python3 - "$wave_json" <<'PY'
import json, sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
runs = payload.get("runs", [])
if not isinstance(runs, list) or not runs:
    print("")
    raise SystemExit(0)
best = sorted(
    [r for r in runs if isinstance(r, dict)],
    key=lambda r: (
        int(r.get("lesson_activations", 0)),
        1 if bool(r.get("passed", False)) else 0,
        -int(r.get("tool_errors", 0)),
    ),
    reverse=True,
)[0]
print(int(best.get("session_id", 0)))
PY
}

run_timeline() {
  local wave_json="$1"
  local output_txt="$2"
  local session_id
  session_id="$(pick_timeline_session "$wave_json")"
  if [[ -z "${session_id}" || "${session_id}" == "0" ]]; then
    echo "No session found for ${wave_json}; skipping timeline."
    return
  fi
  echo
  echo "== Timeline for session ${session_id} (picked from ${wave_json}) =="
  python3 tracks/cli_sqlite/scripts/memory_timeline_demo.py \
    --session "${session_id}" \
    --show-ok-steps \
    --show-all-tools \
    --show-tool-output \
    --show-lessons "${TIMELINE_SHOW_LESSONS}" | tee "${output_txt}"
  echo "Wrote timeline: ${output_txt}"
}

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
if [[ "${AUTO_TIMELINE}" == "1" ]]; then
  run_timeline "${WAVE1_JSON}" "${WAVE1_TIMELINE}"
  run_timeline "${WAVE2_JSON}" "${WAVE2_TIMELINE}"
  run_timeline "${WAVE3_JSON}" "${WAVE3_TIMELINE}"
  echo
  echo "Timeline artifacts:"
  echo "  ${WAVE1_TIMELINE}"
  echo "  ${WAVE2_TIMELINE}"
  echo "  ${WAVE3_TIMELINE}"
else
  echo "== Suggested timeline commands for demo narration =="
  echo "python3 tracks/cli_sqlite/scripts/memory_timeline_demo.py --session $((WAVE1_START + 1)) --show-ok-steps --show-all-tools --show-tool-output --show-lessons ${TIMELINE_SHOW_LESSONS}"
  echo "python3 tracks/cli_sqlite/scripts/memory_timeline_demo.py --session $((WAVE2_START + 1)) --show-ok-steps --show-all-tools --show-tool-output --show-lessons ${TIMELINE_SHOW_LESSONS}"
  echo "python3 tracks/cli_sqlite/scripts/memory_timeline_demo.py --session $((WAVE3_START + 1)) --show-ok-steps --show-all-tools --show-tool-output --show-lessons ${TIMELINE_SHOW_LESSONS}"
fi

if [[ "${AUTO_TOKEN_REPORT}" == "1" ]]; then
  echo
  echo "== Token report (includes prompt/cache tokens, including lessons context) =="
  python3 tracks/cli_sqlite/scripts/report_demo_tokens.py \
    --input-json "${WAVE1_JSON}" \
    --input-json "${WAVE2_JSON}" \
    --input-json "${WAVE3_JSON}" \
    --output-json "${TOKEN_REPORT_JSON}"
  echo "Token report artifact: ${TOKEN_REPORT_JSON}"
fi
echo
echo "Done."
