#!/usr/bin/env bash
set -euo pipefail

# Reports status of the Parallels "Cortex Runner" VM.
# Requires: prlctl (Parallels Desktop CLI)

VM_NAME="${CORTEX_PRL_VM:-Cortex Runner}"

if ! command -v prlctl >/dev/null 2>&1; then
  echo "prlctl not found."
  exit 1
fi

status_line="$(prlctl status "${VM_NAME}" 2>/dev/null)" || {
  echo "status=not_found vm=${VM_NAME}"
  exit 0
}

status="$(echo "${status_line}" | awk '{print $NF}')"
echo "status=${status} vm=${VM_NAME}"

if [[ "${status}" == "running" ]]; then
  # Show IP and uptime
  prlctl list --info "${VM_NAME}" 2>/dev/null | grep -E "^(IP|Uptime|Memory|CPU)" || true
  # Test guest connectivity
  if prlctl exec "${VM_NAME}" echo "guest_reachable=true" 2>/dev/null; then
    :
  else
    echo "guest_reachable=false (tools not ready or not installed)"
  fi
fi
