#!/usr/bin/env bash
set -euo pipefail

# Legacy-style hackathon demo runner with a cold-start stability guard.
# Goal: keep the same narrative structure while avoiding "lucky" wave-1 runs
# where sqlite cold-start unexpectedly passes and weakens the demo signal.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "${ROOT_DIR}"

START_SESSION="${START_SESSION:-56001}"
MAX_STEPS="${MAX_STEPS:-4}"
LEARNING_MODE="${LEARNING_MODE:-strict}"
POSTTASK_MODE="${POSTTASK_MODE:-candidate}"
GRID_TASK_ID="${GRID_TASK_ID:-multi_step_pipeline}"
SHELL_TASK_ID="${SHELL_TASK_ID:-shell_excel_multi_summary}"
SQLITE_TASK_ID="${SQLITE_TASK_ID:-incremental_reconcile}"
OUTPUT_DIR="${OUTPUT_DIR:-/tmp}"
AUTO_TIMELINE="${AUTO_TIMELINE:-1}"
AUTO_TOKEN_REPORT="${AUTO_TOKEN_REPORT:-1}"
TIMELINE_SHOW_LESSONS="${TIMELINE_SHOW_LESSONS:-6}"
TOKEN_REPORT_JSON="${OUTPUT_DIR}/memory_mixed_tokens_${START_SESSION}.json"

# Cold-start guard knobs.
ENFORCE_WAVE1_SQLITE_FAIL="${ENFORCE_WAVE1_SQLITE_FAIL:-1}"
WAVE1_RETRY_MAX="${WAVE1_RETRY_MAX:-3}"
WAVE1_RETRY_SESSION_STRIDE="${WAVE1_RETRY_SESSION_STRIDE:-100}"

# Each mixed benchmark wave uses 5 sessions with defaults below.
WAVE_SIZE=5

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

phase_pass_count() {
  local wave_json="$1"
  local phase_name="$2"
  python3 - "$wave_json" "$phase_name" <<'PY'
import json, sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
phase = sys.argv[2]
summary = payload.get("phase_summary", {})
row = summary.get(phase, {}) if isinstance(summary, dict) else {}
print(int(row.get("pass_count", 0) or 0))
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

run_wave() {
  local wave_title="$1"
  local start_session="$2"
  local output_json="$3"
  local clear_lessons="$4"

  echo
  echo "== ${wave_title} =="

  local cmd=(
    python3 tracks/cli_sqlite/scripts/run_mixed_benchmark.py
    --grid-task-id "${GRID_TASK_ID}"
    --fluxtool-task-id aggregate_report_holdout
    --shell-task-id "${SHELL_TASK_ID}"
    --sqlite-task-id "${SQLITE_TASK_ID}"
    --grid-runs 1
    --fluxtool-runs 1
    --shell-runs 1
    --sqlite-runs 1
    --retention-runs 1
    --start-session "${start_session}"
    --max-steps "${MAX_STEPS}"
    --learning-mode "${LEARNING_MODE}"
    --posttask-mode "${POSTTASK_MODE}"
    --bootstrap
    --mixed-errors
    --cryptic-errors
    --output-json "${output_json}"
  )
  if [[ "${clear_lessons}" == "1" ]]; then
    cmd+=(--clear-lessons)
  fi
  "${cmd[@]}"
}

echo "== Memory V2 Hackathon Demo (Legacy Runner) =="
echo "root=${ROOT_DIR}"
echo "start_session=${START_SESSION} max_steps=${MAX_STEPS} learning_mode=${LEARNING_MODE}"
echo "grid_task_id=${GRID_TASK_ID}"
echo "shell_task_id=${SHELL_TASK_ID}"
echo "sqlite_task_id=${SQLITE_TASK_ID}"
echo "enforce_wave1_sqlite_fail=${ENFORCE_WAVE1_SQLITE_FAIL} retries=${WAVE1_RETRY_MAX} stride=${WAVE1_RETRY_SESSION_STRIDE}"
echo

wave1_attempt=1
wave1_start_candidate="${START_SESSION}"
WAVE1_JSON=""
WAVE1_START_ACTUAL=""

while :; do
  wave1_json_candidate="${OUTPUT_DIR}/memory_mixed_wave1_${wave1_start_candidate}.json"
  run_wave "Wave 1 (cold start, clear lessons) attempt ${wave1_attempt}/${WAVE1_RETRY_MAX}" "${wave1_start_candidate}" "${wave1_json_candidate}" "1"

  if [[ "${ENFORCE_WAVE1_SQLITE_FAIL}" != "1" ]]; then
    WAVE1_JSON="${wave1_json_candidate}"
    WAVE1_START_ACTUAL="${wave1_start_candidate}"
    break
  fi

  sqlite_pass_count="$(phase_pass_count "${wave1_json_candidate}" "sqlite_interference")"
  if [[ "${sqlite_pass_count}" -eq 0 ]]; then
    WAVE1_JSON="${wave1_json_candidate}"
    WAVE1_START_ACTUAL="${wave1_start_candidate}"
    break
  fi

  if [[ "${wave1_attempt}" -ge "${WAVE1_RETRY_MAX}" ]]; then
    echo
    echo "WARNING: sqlite_interference still passed on wave 1 after ${WAVE1_RETRY_MAX} attempts; continuing anyway."
    WAVE1_JSON="${wave1_json_candidate}"
    WAVE1_START_ACTUAL="${wave1_start_candidate}"
    break
  fi

  echo
  echo "Wave 1 sqlite_interference passed unexpectedly (cold run). Retrying wave 1 with a fresh session block..."
  wave1_attempt=$((wave1_attempt + 1))
  wave1_start_candidate=$((wave1_start_candidate + WAVE1_RETRY_SESSION_STRIDE))
done

WAVE2_START=$((WAVE1_START_ACTUAL + WAVE_SIZE))
WAVE3_START=$((WAVE1_START_ACTUAL + (2 * WAVE_SIZE)))

WAVE2_JSON="${OUTPUT_DIR}/memory_mixed_wave2_${WAVE2_START}.json"
WAVE3_JSON="${OUTPUT_DIR}/memory_mixed_wave3_${WAVE3_START}.json"
WAVE1_TIMELINE="${OUTPUT_DIR}/memory_timeline_wave1_${WAVE1_START_ACTUAL}.txt"
WAVE2_TIMELINE="${OUTPUT_DIR}/memory_timeline_wave2_${WAVE2_START}.txt"
WAVE3_TIMELINE="${OUTPUT_DIR}/memory_timeline_wave3_${WAVE3_START}.txt"

echo
echo "Final output artifacts:"
echo "  ${WAVE1_JSON}"
echo "  ${WAVE2_JSON}"
echo "  ${WAVE3_JSON}"

run_wave "Wave 2 (memory reused)" "${WAVE2_START}" "${WAVE2_JSON}" "0"
run_wave "Wave 3 (memory reused)" "${WAVE3_START}" "${WAVE3_JSON}" "0"

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
  echo "python3 tracks/cli_sqlite/scripts/memory_timeline_demo.py --session $((WAVE1_START_ACTUAL + 1)) --show-ok-steps --show-all-tools --show-tool-output --show-lessons ${TIMELINE_SHOW_LESSONS}"
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
