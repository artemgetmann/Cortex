#!/usr/bin/env bash
set -euo pipefail

# Hackathon demo runner.
# Purpose:
# - Run 3 sequential mixed-benchmark waves with shared memory.
# - Optionally produce cleaner demo output via --pretty.
# - Optionally auto-generate timeline traces and token summaries.

usage() {
  cat <<'EOF'
Usage:
  bash tracks/cli_sqlite/scripts/run_hackathon_demo.sh [--pretty]

Options:
  --pretty      suppress giant JSON dumps and print compact wave summaries
  -h, --help    show this help

Env knobs:
  START_SESSION=56001
  MAX_STEPS=5
  LEARNING_MODE=strict
  POSTTASK_MODE=candidate
  SQLITE_TASK_ID=incremental_reconcile
  OUTPUT_DIR=/tmp
  AUTO_TIMELINE=0|1
  AUTO_TOKEN_REPORT=0|1
  TIMELINE_SHOW_LESSONS=6
  ENFORCE_WAVE1_SQLITE_FAIL=1
  WAVE1_RETRY_MAX=3
  WAVE1_RETRY_SESSION_STRIDE=100
  PRETTY_MODE=0|1  # same effect as --pretty
EOF
}

PRETTY_MODE="${PRETTY_MODE:-0}"
while (($#)); do
  case "$1" in
    --pretty)
      PRETTY_MODE=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      usage
      exit 1
      ;;
  esac
  shift
done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "${ROOT_DIR}"

START_SESSION="${START_SESSION:-56001}"
MAX_STEPS="${MAX_STEPS:-5}"
LEARNING_MODE="${LEARNING_MODE:-strict}"
POSTTASK_MODE="${POSTTASK_MODE:-candidate}"
SQLITE_TASK_ID="${SQLITE_TASK_ID:-incremental_reconcile}"
OUTPUT_DIR="${OUTPUT_DIR:-/tmp}"
AUTO_TIMELINE="${AUTO_TIMELINE:-1}"
AUTO_TOKEN_REPORT="${AUTO_TOKEN_REPORT:-1}"
TIMELINE_SHOW_LESSONS="${TIMELINE_SHOW_LESSONS:-6}"
ENFORCE_WAVE1_SQLITE_FAIL="${ENFORCE_WAVE1_SQLITE_FAIL:-1}"
WAVE1_RETRY_MAX="${WAVE1_RETRY_MAX:-3}"
WAVE1_RETRY_SESSION_STRIDE="${WAVE1_RETRY_SESSION_STRIDE:-100}"

# Each mixed benchmark wave uses 5 sessions with defaults below.
WAVE_SIZE=5
TOKEN_REPORT_JSON="${OUTPUT_DIR}/memory_mixed_tokens_${START_SESSION}.json"

WAVE1_START_ACTUAL=""
WAVE2_START=""
WAVE3_START=""
WAVE1_JSON=""
WAVE2_JSON=""
WAVE3_JSON=""
WAVE1_TIMELINE=""
WAVE2_TIMELINE=""
WAVE3_TIMELINE=""

MIXED_BENCH_EXTRA_ARGS=()
if [[ "${PRETTY_MODE}" == "1" ]]; then
  MIXED_BENCH_EXTRA_ARGS+=(--no-print-json-summary)
fi

print_pretty_wave() {
  local wave_label="$1"
  local json_path="$2"
  python3 - "${wave_label}" "${json_path}" <<'PY'
import json
import sys
from pathlib import Path

label = sys.argv[1]
path = Path(sys.argv[2])
payload = json.loads(path.read_text(encoding="utf-8"))
overall = payload.get("overall_summary", {})
phase = payload.get("phase_summary", {})

def _f(v, nd=2):
    try:
        return f"{float(v):.{nd}f}"
    except Exception:
        return "n/a"

def _pct(v):
    try:
        return f"{100.0 * float(v):.1f}%"
    except Exception:
        return "n/a"

print(f"\n== {label} Pretty Summary ==")
print(
    "overall: "
    f"pass_rate={_pct(overall.get('pass_rate'))} "
    f"score={_f(overall.get('mean_score'))} "
    f"steps={_f(overall.get('mean_steps'))} "
    f"errs={_f(overall.get('mean_tool_errors'))} "
    f"acts={int(overall.get('lesson_activations_total') or 0)} "
    f"time_s={_f(overall.get('elapsed_s_total'))}"
)
print("phase snapshots:")
for name in (
    "grid_warmup",
    "fluxtool_interference",
    "shell_excel_interference",
    "sqlite_interference",
    "grid_retention",
):
    s = phase.get(name, {})
    print(
        f"- {name}: pass={_pct(s.get('pass_rate'))} "
        f"score={_f(s.get('mean_score'))} "
        f"steps={_f(s.get('mean_steps'))} "
        f"errs={_f(s.get('mean_tool_errors'))} "
        f"acts={int(s.get('lesson_activations_total') or 0)}"
    )
PY
}

pick_timeline_session() {
  local wave_json="$1"
  python3 - "$wave_json" <<'PY'
import json
import sys
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
import json
import sys
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
  local wave_start="$2"
  local wave_json="$3"
  local clear_flag="$4"
  local clear_label="$5"

  echo
  echo "== ${wave_title} (${clear_label}) =="
  local cmd=(
    python3 tracks/cli_sqlite/scripts/run_mixed_benchmark.py
    --grid-task-id aggregate_report
    --fluxtool-task-id aggregate_report_holdout
    --shell-task-id shell_excel_build_report
    --sqlite-task-id "${SQLITE_TASK_ID}"
    --grid-runs 1
    --fluxtool-runs 1
    --shell-runs 1
    --sqlite-runs 1
    --retention-runs 1
    --start-session "${wave_start}"
    --max-steps "${MAX_STEPS}"
    --learning-mode "${LEARNING_MODE}"
    --posttask-mode "${POSTTASK_MODE}"
    --bootstrap
    --mixed-errors
    --cryptic-errors
    --output-json "${wave_json}"
  )
  if [[ "${clear_flag}" == "1" ]]; then
    cmd+=(--clear-lessons)
  fi
  if [[ "${#MIXED_BENCH_EXTRA_ARGS[@]}" -gt 0 ]]; then
    cmd+=("${MIXED_BENCH_EXTRA_ARGS[@]}")
  fi
  "${cmd[@]}"

  if [[ "${PRETTY_MODE}" == "1" ]]; then
    print_pretty_wave "${wave_title}" "${wave_json}"
  fi
}

echo "== Memory V2 Hackathon Demo =="
echo "root=${ROOT_DIR}"
echo "start_session=${START_SESSION} max_steps=${MAX_STEPS} learning_mode=${LEARNING_MODE}"
echo "sqlite_task_id=${SQLITE_TASK_ID}"
echo "enforce_wave1_sqlite_fail=${ENFORCE_WAVE1_SQLITE_FAIL} retries=${WAVE1_RETRY_MAX} stride=${WAVE1_RETRY_SESSION_STRIDE}"
echo "pretty_mode=${PRETTY_MODE} auto_timeline=${AUTO_TIMELINE} auto_token_report=${AUTO_TOKEN_REPORT}"
echo

wave1_attempt=1
wave1_start_candidate="${START_SESSION}"
while :; do
  wave1_json_candidate="${OUTPUT_DIR}/memory_mixed_wave1_${wave1_start_candidate}.json"
  run_wave "Wave 1" "${wave1_start_candidate}" "${wave1_json_candidate}" "1" "cold start, clear lessons (attempt ${wave1_attempt}/${WAVE1_RETRY_MAX})"

  if [[ "${ENFORCE_WAVE1_SQLITE_FAIL}" != "1" ]]; then
    WAVE1_START_ACTUAL="${wave1_start_candidate}"
    WAVE1_JSON="${wave1_json_candidate}"
    break
  fi

  sqlite_pass_count="$(phase_pass_count "${wave1_json_candidate}" "sqlite_interference")"
  if [[ "${sqlite_pass_count}" -eq 0 ]]; then
    WAVE1_START_ACTUAL="${wave1_start_candidate}"
    WAVE1_JSON="${wave1_json_candidate}"
    break
  fi

  if [[ "${wave1_attempt}" -ge "${WAVE1_RETRY_MAX}" ]]; then
    echo
    echo "WARNING: sqlite_interference still passed on wave 1 after ${WAVE1_RETRY_MAX} attempts; continuing anyway."
    WAVE1_START_ACTUAL="${wave1_start_candidate}"
    WAVE1_JSON="${wave1_json_candidate}"
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
echo

run_wave "Wave 2" "${WAVE2_START}" "${WAVE2_JSON}" "0" "memory reused"
run_wave "Wave 3" "${WAVE3_START}" "${WAVE3_JSON}" "0" "memory reused"

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
  if [[ "${PRETTY_MODE}" == "1" ]]; then
    python3 - "${TOKEN_REPORT_JSON}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
grand = payload.get("grand_total", {})
print("\n== Token Grand Total (Pretty) ==")
print(
    f"runs={int(grand.get('runs') or 0)} "
    f"in={int(grand.get('input_tokens') or 0)} "
    f"out={int(grand.get('output_tokens') or 0)} "
    f"cache_read={int(grand.get('cache_read_input_tokens') or 0)} "
    f"cache_create={int(grand.get('cache_creation_input_tokens') or 0)} "
    f"all={int(grand.get('total_with_cache_tokens') or 0)}"
)
PY
  fi
  echo "Token report artifact: ${TOKEN_REPORT_JSON}"
fi

echo
echo "Done."
