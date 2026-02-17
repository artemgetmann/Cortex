#!/usr/bin/env bash
set -euo pipefail

# Run 3 memory waves for a single domain/task only.
# Wave 1 clears lessons, waves 2-3 reuse memory.
#
# Examples:
#   bash tracks/cli_sqlite/scripts/run_tool_three_waves.sh \
#     --domain gridtool --task-id multi_step_pipeline --start-session 99501 --max-steps 4
#
#   bash tracks/cli_sqlite/scripts/run_tool_three_waves.sh \
#     --domain shell --task-id shell_excel_multi_summary --start-session 99601 --max-steps 4

usage() {
  cat <<'EOF'
Usage:
  bash tracks/cli_sqlite/scripts/run_tool_three_waves.sh \
    --domain <gridtool|fluxtool|shell|sqlite|artic> \
    --task-id <task_id> \
    [--start-session 99501] \
    [--max-steps 4] \
    [--learning-mode strict] \
    [--posttask-mode candidate] \
    [--output-dir /tmp]
EOF
}

DOMAIN=""
TASK_ID=""
START_SESSION="99501"
MAX_STEPS="4"
LEARNING_MODE="strict"
POSTTASK_MODE="candidate"
OUTPUT_DIR="/tmp"

while (($#)); do
  case "$1" in
    --domain) DOMAIN="${2:-}"; shift 2 ;;
    --task-id) TASK_ID="${2:-}"; shift 2 ;;
    --start-session) START_SESSION="${2:-}"; shift 2 ;;
    --max-steps) MAX_STEPS="${2:-}"; shift 2 ;;
    --learning-mode) LEARNING_MODE="${2:-}"; shift 2 ;;
    --posttask-mode) POSTTASK_MODE="${2:-}"; shift 2 ;;
    --output-dir) OUTPUT_DIR="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -z "${DOMAIN}" || -z "${TASK_ID}" ]]; then
  echo "--domain and --task-id are required" >&2
  usage
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "${ROOT_DIR}"

grid_runs=0
flux_runs=0
shell_runs=0
sqlite_runs=0
retention_runs=0

case "${DOMAIN}" in
  gridtool) grid_runs=1 ;;
  fluxtool) flux_runs=1 ;;
  shell) shell_runs=1 ;;
  sqlite) sqlite_runs=1 ;;
  artic) sqlite_runs=0; shell_runs=0; flux_runs=0; grid_runs=0 ;; # handled below
  *) echo "Unsupported domain: ${DOMAIN}" >&2; exit 1 ;;
esac

if [[ "${DOMAIN}" == "artic" ]]; then
  # run_mixed_benchmark has no artic slot; use sqlite slot with domain-specific task path via task id mapping
  # Not supported in this helper for now.
  echo "Domain 'artic' is not supported by this helper yet. Use run_cli_agent or run_mixed_benchmark directly." >&2
  exit 1
fi

for wave in 1 2 3; do
  sid=$((START_SESSION + wave - 1))
  out_json="${OUTPUT_DIR}/tool3_${DOMAIN}_${TASK_ID}_wave${wave}_${sid}.json"
  clear_flag=()
  if [[ "${wave}" -eq 1 ]]; then
    clear_flag=(--clear-lessons)
  fi

  python3 tracks/cli_sqlite/scripts/run_mixed_benchmark.py \
    --grid-task-id "${TASK_ID}" \
    --fluxtool-task-id "${TASK_ID}" \
    --shell-task-id "${TASK_ID}" \
    --sqlite-task-id "${TASK_ID}" \
    --grid-runs "${grid_runs}" \
    --fluxtool-runs "${flux_runs}" \
    --shell-runs "${shell_runs}" \
    --sqlite-runs "${sqlite_runs}" \
    --retention-runs "${retention_runs}" \
    --start-session "${sid}" \
    --max-steps "${MAX_STEPS}" \
    --learning-mode "${LEARNING_MODE}" \
    --posttask-mode "${POSTTASK_MODE}" \
    --bootstrap \
    --mixed-errors \
    --cryptic-errors \
    "${clear_flag[@]}" \
    --output-json "${out_json}" \
    --no-print-json-summary

  python3 - "${out_json}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
runs = payload.get("runs", [])
if not runs:
    print(f"{sys.argv[1]} -> no runs")
    raise SystemExit(0)
r = runs[0]
print(
    f"{Path(sys.argv[1]).name} -> "
    f"pass={bool(r.get('passed'))} "
    f"score={float(r.get('score', 0.0)):.3f} "
    f"steps={int(r.get('steps', 0))} "
    f"errors={int(r.get('tool_errors', 0))} "
    f"lessons_in={int(r.get('lessons_loaded', 0))} "
    f"acts={int(r.get('lesson_activations', 0))}"
)
PY
done

