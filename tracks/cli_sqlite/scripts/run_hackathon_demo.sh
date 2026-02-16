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
  OUTPUT_DIR=/tmp
  AUTO_TIMELINE=0|1
  AUTO_TOKEN_REPORT=0|1
  TIMELINE_SHOW_LESSONS=6
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
OUTPUT_DIR="${OUTPUT_DIR:-/tmp}"
AUTO_TIMELINE="${AUTO_TIMELINE:-0}"
AUTO_TOKEN_REPORT="${AUTO_TOKEN_REPORT:-0}"
TIMELINE_SHOW_LESSONS="${TIMELINE_SHOW_LESSONS:-6}"

# Each mixed benchmark wave uses 5 sessions with defaults below.
WAVE_SIZE=5
WAVE1_START="${START_SESSION}"
WAVE2_START="$((START_SESSION + WAVE_SIZE))"
WAVE3_START="$((START_SESSION + (2 * WAVE_SIZE)))"

WAVE1_JSON="${OUTPUT_DIR}/memory_mixed_wave1_${WAVE1_START}.json"
WAVE2_JSON="${OUTPUT_DIR}/memory_mixed_wave2_${WAVE2_START}.json"
WAVE3_JSON="${OUTPUT_DIR}/memory_mixed_wave3_${WAVE3_START}.json"
TOKEN_JSON="${OUTPUT_DIR}/memory_mixed_tokens_${START_SESSION}.json"
TIMELINE1_TXT="${OUTPUT_DIR}/memory_timeline_wave1_${WAVE1_START}.txt"
TIMELINE2_TXT="${OUTPUT_DIR}/memory_timeline_wave2_${WAVE2_START}.txt"
TIMELINE3_TXT="${OUTPUT_DIR}/memory_timeline_wave3_${WAVE3_START}.txt"

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
        return f"{100.0*float(v):.1f}%"
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
for name in ("grid_warmup", "fluxtool_interference", "shell_excel_interference", "sqlite_interference", "grid_retention"):
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
    --sqlite-task-id import_aggregate
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
echo "pretty_mode=${PRETTY_MODE} auto_timeline=${AUTO_TIMELINE} auto_token_report=${AUTO_TOKEN_REPORT}"
echo "outputs:"
echo "  ${WAVE1_JSON}"
echo "  ${WAVE2_JSON}"
echo "  ${WAVE3_JSON}"
echo

run_wave "Wave 1" "${WAVE1_START}" "${WAVE1_JSON}" "1" "cold start, clear lessons"
run_wave "Wave 2" "${WAVE2_START}" "${WAVE2_JSON}" "0" "memory reused"
run_wave "Wave 3" "${WAVE3_START}" "${WAVE3_JSON}" "0" "memory reused"

if [[ "${AUTO_TIMELINE}" == "1" ]]; then
  echo
  echo "== Auto timeline generation =="
  python3 tracks/cli_sqlite/scripts/memory_timeline_demo.py --session "$((WAVE1_START + 1))" --show-ok-steps --show-all-tools --show-tool-output --show-lessons "${TIMELINE_SHOW_LESSONS}" > "${TIMELINE1_TXT}"
  python3 tracks/cli_sqlite/scripts/memory_timeline_demo.py --session "$((WAVE2_START + 1))" --show-ok-steps --show-all-tools --show-tool-output --show-lessons "${TIMELINE_SHOW_LESSONS}" > "${TIMELINE2_TXT}"
  python3 tracks/cli_sqlite/scripts/memory_timeline_demo.py --session "$((WAVE3_START + 1))" --show-ok-steps --show-all-tools --show-tool-output --show-lessons "${TIMELINE_SHOW_LESSONS}" > "${TIMELINE3_TXT}"
  echo "wrote: ${TIMELINE1_TXT}"
  echo "wrote: ${TIMELINE2_TXT}"
  echo "wrote: ${TIMELINE3_TXT}"
else
  echo
  echo "== Suggested timeline commands for demo narration =="
  echo "python3 tracks/cli_sqlite/scripts/memory_timeline_demo.py --session $((WAVE1_START + 1)) --show-ok-steps --show-all-tools --show-tool-output --show-lessons ${TIMELINE_SHOW_LESSONS}"
  echo "python3 tracks/cli_sqlite/scripts/memory_timeline_demo.py --session $((WAVE2_START + 1)) --show-ok-steps --show-all-tools --show-tool-output --show-lessons ${TIMELINE_SHOW_LESSONS}"
  echo "python3 tracks/cli_sqlite/scripts/memory_timeline_demo.py --session $((WAVE3_START + 1)) --show-ok-steps --show-all-tools --show-tool-output --show-lessons ${TIMELINE_SHOW_LESSONS}"
fi

if [[ "${AUTO_TOKEN_REPORT}" == "1" ]]; then
  echo
  echo "== Auto token report =="
  python3 tracks/cli_sqlite/scripts/report_demo_tokens.py \
    --input-json "${WAVE1_JSON}" \
    --input-json "${WAVE2_JSON}" \
    --input-json "${WAVE3_JSON}" \
    --output-json "${TOKEN_JSON}"
  if [[ "${PRETTY_MODE}" == "1" ]]; then
    python3 - "${TOKEN_JSON}" <<'PY'
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
  echo "wrote: ${TOKEN_JSON}"
fi

echo
echo "Done."
