#!/usr/bin/env bash
set -euo pipefail

# Gracefully stops the Parallels "Cortex Runner" VM.
# Falls back to kill after 60s timeout.
# Requires: prlctl (Parallels Desktop CLI)

VM_NAME="${CORTEX_PRL_VM:-Cortex Runner}"

if ! command -v prlctl >/dev/null 2>&1; then
  echo "prlctl not found."
  exit 1
fi

status="$(prlctl status "${VM_NAME}" 2>/dev/null | awk '{print $NF}')" || {
  echo "VM '${VM_NAME}' not found."
  exit 0
}

if [[ "${status}" == "stopped" ]]; then
  echo "VM already stopped."
  exit 0
fi

echo "Stopping VM '${VM_NAME}' gracefully..."
prlctl stop "${VM_NAME}" 2>/dev/null && {
  echo "VM stopped."
  exit 0
}

# Graceful stop failed — force it
echo "Graceful stop timed out, forcing..."
prlctl stop "${VM_NAME}" --kill 2>/dev/null || true

sleep 2
final="$(prlctl status "${VM_NAME}" 2>/dev/null | awk '{print $NF}')"
if [[ "${final}" == "stopped" ]]; then
  echo "VM force-stopped."
else
  echo "VM in unexpected state: ${final}"
  exit 1
fi
