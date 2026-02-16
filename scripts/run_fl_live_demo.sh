#!/usr/bin/env bash
set -euo pipefail

# Simple live demo runner for FL Studio computer-use.
# Usage:
#   ./scripts/run_fl_live_demo.sh [session_id] [max_steps]
#
# Defaults:
#   session_id: current unix timestamp modulo 100000
#   max_steps: 12

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION_ID="${1:-$(( $(date +%s) % 100000 ))}"
MAX_STEPS="${2:-12}"
REF_IMAGE="${ROOT_DIR}/docs/references/fl-studio/kick-four-on-floor-reference.png"

if [[ ! -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  echo "Missing virtualenv python at ${ROOT_DIR}/.venv/bin/python"
  echo "Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

if [[ ! -f "${REF_IMAGE}" ]]; then
  echo "Reference image missing: ${REF_IMAGE}"
  echo "Add a correct FL screenshot there before running the demo."
  exit 1
fi

TASK="In FL Studio, press F6 to open Channel Rack, create a 4-on-the-floor kick pattern on 808 Kick by activating steps 1,5,9,13, then press Space to start playback and press Space again to stop."

echo "Running FL live demo..."
echo "session=${SESSION_ID} max_steps=${MAX_STEPS}"
echo "reference=${REF_IMAGE}"

CORTEX_FL_REFERENCE_IMAGE="${REF_IMAGE}" \
  "${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/run_agent.py" \
  --task "${TASK}" \
  --session "${SESSION_ID}" \
  --max-steps "${MAX_STEPS}" \
  --verbose

METRICS="${ROOT_DIR}/sessions/session-${SESSION_ID}/metrics.json"
if [[ -f "${METRICS}" ]]; then
  echo ""
  echo "Summary:"
  "${ROOT_DIR}/.venv/bin/python" - <<'PY' "${METRICS}"
import json, sys
path = sys.argv[1]
m = json.load(open(path, "r", encoding="utf-8"))
print(f"eval_final_verdict={m.get('eval_final_verdict')}")
print(f"eval_passed={m.get('eval_passed')} score={m.get('eval_score')}")
print(f"eval_det_passed={m.get('eval_det_passed')} judge_passed={m.get('judge_passed')}")
print(f"steps={m.get('steps')} tool_errors={m.get('tool_errors')} loop_guard_blocks={m.get('loop_guard_blocks')}")
PY
  echo "metrics_path=${METRICS}"
fi
