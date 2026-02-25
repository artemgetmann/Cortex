#!/usr/bin/env bash
set -euo pipefail

# Guest-side helper for FL benchmark runs via Terminal/TCC-safe context.
# Usage (inside guest shell):
#   /tmp/prl_fl_benchmark_runner.sh --session 9400 --runs 5 --max-steps 12 --effort medium --posttask-mode direct --output /Users/cortex/CortexLocal/sessions/fl_curve_9400.json

SESSION=9400
RUNS=5
MAX_STEPS=12
EFFORT=medium
POSTTASK_MODE=direct
MODEL=claude-opus-4-6
BACKEND=claude_print
OUTPUT="/Users/cortex/CortexLocal/sessions/fl_curve_${SESSION}_5runs_direct_medium.json"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --session) SESSION="$2"; shift ;;
    --runs) RUNS="$2"; shift ;;
    --max-steps) MAX_STEPS="$2"; shift ;;
    --effort) EFFORT="$2"; shift ;;
    --posttask-mode) POSTTASK_MODE="$2"; shift ;;
    --model) MODEL="$2"; shift ;;
    --backend) BACKEND="$2"; shift ;;
    --output) OUTPUT="$2"; shift ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
  shift
done

cd /Users/cortex/CortexLocal

# 1) Try to wake/unlock first. If already unlocked, this usually no-ops.
osascript -e 'tell application "System Events" to keystroke "macos"' -e 'tell application "System Events" to key code 36' || true
sleep 1

# 2) Keep FL visible and Terminal out of the way.
osascript -e 'tell application "Terminal" to set miniaturized of every window to true' || true
osascript -e 'tell application "FL Studio" to activate' || true
sleep 1

# 3) Fail fast if lock window is frontmost.
frontmost="$(osascript -e 'tell application "System Events" to get name of first process whose frontmost is true' 2>/dev/null || true)"
if [[ "${frontmost}" == "loginwindow" || "${frontmost}" == "ScreenSaverEngine" ]]; then
  echo "preflight_failed=lock_screen_detected frontmost=${frontmost}"
  exit 3
fi

# 4) Prevent idle sleep while benchmark runs.
CORTEX_CLAUDE_PRINT_TIMEOUT_S=120 \
  caffeinate -dimsu /Users/cortex/.venv-cortex/bin/python scripts/run_fl_benchmark.py \
    --start-session "$SESSION" \
    --runs "$RUNS" \
    --max-steps "$MAX_STEPS" \
    --llm-backend "$BACKEND" \
    --model "$MODEL" \
    --effort "$EFFORT" \
    --posttask-mode "$POSTTASK_MODE" \
    --output-json "$OUTPUT" \
    --verbose
