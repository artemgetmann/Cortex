#!/usr/bin/env bash
set -euo pipefail

# Run a command inside the guest's Terminal app via prlctl.
#
# Why this exists:
# - Direct `prlctl exec` runs under a non-interactive guest context.
# - macOS TCC checks (Accessibility/Screen Recording) often fail in that context.
# - Running through guest Terminal reuses the GUI app identity you already granted.
#
# Usage examples:
#   ./scripts/vm/prl_terminal_run.sh --cmd 'echo hello'
#   ./scripts/vm/prl_terminal_run.sh --cmd 'cd /Users/cortex/CortexLocal && /Users/cortex/.venv-cortex/bin/python scripts/run_agent.py --task "Create a 4-on-the-floor kick drum pattern" --session 9310 --max-steps 12 --verbose' --wait
#
# Environment:
#   CORTEX_PRL_VM          VM name (default: "Cortex Runner")
#   CORTEX_PRL_USER        Guest user (default: "cortex")
#   CORTEX_PRL_PASS        Guest password (default: "macos")
#   CORTEX_PRL_WAIT_SEC    Wait timeout when --wait is used (default: 900)
#   CORTEX_PRL_LOG_PATH    Guest log path (default: /tmp/cortex_terminal_cmd.log)

VM_NAME="${CORTEX_PRL_VM:-Cortex Runner}"
VM_USER="${CORTEX_PRL_USER:-cortex}"
VM_PASS="${CORTEX_PRL_PASS:-macos}"
WAIT_TIMEOUT="${CORTEX_PRL_WAIT_SEC:-900}"
LOG_PATH="${CORTEX_PRL_LOG_PATH:-/tmp/cortex_terminal_cmd.log}"

WAIT_MODE=0
CMD=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cmd)
      shift
      CMD="${1:-}"
      ;;
    --wait)
      WAIT_MODE=1
      ;;
    --timeout)
      shift
      WAIT_TIMEOUT="${1:-$WAIT_TIMEOUT}"
      ;;
    --log)
      shift
      LOG_PATH="${1:-$LOG_PATH}"
      ;;
    -h|--help)
      sed -n '1,120p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $1"
      echo "Use --help for usage."
      exit 2
      ;;
  esac
  shift
done

if [[ -z "${CMD}" ]]; then
  echo "Missing --cmd."
  echo "Example:"
  echo "  ./scripts/vm/prl_terminal_run.sh --cmd 'echo hello' --wait"
  exit 2
fi

if ! command -v prlctl >/dev/null 2>&1; then
  echo "prlctl not found. Install Parallels Desktop first."
  exit 1
fi

status="$(prlctl status "${VM_NAME}" 2>/dev/null | awk '{print $NF}')" || {
  echo "VM '${VM_NAME}' not found."
  echo "  prlctl list --all"
  exit 1
}
if [[ "${status}" != "running" ]]; then
  echo "VM '${VM_NAME}' is not running (status=${status})."
  echo "  ./scripts/vm/prl_start.sh"
  exit 1
fi

RUNNER_PATH="/tmp/cortex_terminal_runner.sh"
CMD_PATH="/tmp/cortex_terminal_cmd.txt"

# Keep the runner tiny and deterministic; command text lives in a separate file.
runner_script="$(cat <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
CMD_FILE="${1:?missing cmd file path}"
LOG_FILE="${2:?missing log file path}"
if [[ ! -f "${CMD_FILE}" ]]; then
  echo "Missing command file: ${CMD_FILE}" >&2
  exit 2
fi

# Keep a stable PATH so guest shell tools are resolvable in Terminal sessions.
export PATH="/usr/local/bin:/opt/homebrew/bin:$HOME/.local/bin:$PATH"
CMD="$(cat "${CMD_FILE}")"

# Execute inside zsh login shell so behavior matches interactive Terminal.
# Keep explicit rc capture so caller can detect completion reliably.
set +e
/bin/zsh -lc "${CMD}" > "${LOG_FILE}" 2>&1
rc=$?
set -e
printf '__CORTEX_EXIT__=%s\n' "${rc}" >> "${LOG_FILE}"
exit "${rc}"
EOF
)"

b64_runner="$(printf '%s' "${runner_script}" | base64 | tr -d '\n')"
b64_cmd="$(printf '%s' "${CMD}" | base64 | tr -d '\n')"

prlctl exec "${VM_NAME}" --user "${VM_USER}" --password "${VM_PASS}" \
  "bash -lc 'echo \"${b64_runner}\" | base64 -d > ${RUNNER_PATH} && chmod +x ${RUNNER_PATH} && echo \"${b64_cmd}\" | base64 -d > ${CMD_PATH}'"

# Launch in guest Terminal to inherit TCC grants from that app identity.
prlctl exec "${VM_NAME}" --user "${VM_USER}" --password "${VM_PASS}" \
  "bash -lc 'osascript -e \"tell application \\\"Terminal\\\" to activate\" -e \"tell application \\\"Terminal\\\" to do script \\\"bash ${RUNNER_PATH} ${CMD_PATH} ${LOG_PATH}\\\"\"'"

echo "started=true vm=${VM_NAME}"
echo "log_path=${LOG_PATH}"

if [[ "${WAIT_MODE}" -ne 1 ]]; then
  echo "hint: add --wait to block until completion."
  exit 0
fi

deadline=$(( $(date +%s) + WAIT_TIMEOUT ))
while [[ "$(date +%s)" -lt "${deadline}" ]]; do
  marker="$(
    prlctl exec "${VM_NAME}" --user "${VM_USER}" --password "${VM_PASS}" \
      "bash -lc 'test -f ${LOG_PATH} && grep -E \"__CORTEX_EXIT__=\" ${LOG_PATH} | tail -n1 || true'" \
      2>/dev/null || true
  )"
  if [[ -n "${marker}" ]]; then
    code="${marker#*=}"
    echo "completed=true exit_code=${code}"
    prlctl exec "${VM_NAME}" --user "${VM_USER}" --password "${VM_PASS}" \
      "bash -lc 'tail -n 120 ${LOG_PATH} || true'"
    exit "${code}"
  fi
  sleep 2
done

echo "completed=false timeout=${WAIT_TIMEOUT}s"
echo "Use this to inspect progress:"
echo "  prlctl exec \"${VM_NAME}\" --user \"${VM_USER}\" --password \"***\" \"bash -lc 'tail -n 120 ${LOG_PATH}'\""
exit 124
