#!/usr/bin/env bash
set -euo pipefail

# Starts the Parallels "Cortex Runner" VM in headless mode.
# Requires: prlctl (Parallels Desktop CLI)

VM_NAME="${CORTEX_PRL_VM:-Cortex Runner}"

if ! command -v prlctl >/dev/null 2>&1; then
  echo "prlctl not found. Install Parallels Desktop first."
  exit 1
fi

status="$(prlctl status "${VM_NAME}" 2>/dev/null | awk '{print $NF}')" || {
  echo "VM '${VM_NAME}' not found. Create it in Parallels first."
  echo "  prlctl list --all"
  exit 1
}

if [[ "${status}" == "running" ]]; then
  echo "VM already running."
  prlctl exec "${VM_NAME}" uname -a 2>/dev/null || true
  exit 0
fi

if [[ "${status}" == "suspended" ]]; then
  echo "Resuming suspended VM..."
  prlctl resume "${VM_NAME}"
else
  echo "Starting VM '${VM_NAME}' (headless)..."
  prlctl start "${VM_NAME}" --headless 2>/dev/null || prlctl start "${VM_NAME}"
fi

# Wait for VM to be running (up to 30s)
for i in {1..30}; do
  s="$(prlctl status "${VM_NAME}" 2>/dev/null | awk '{print $NF}')"
  if [[ "${s}" == "running" ]]; then
    echo "VM started successfully."
    prlctl list --info "${VM_NAME}" 2>/dev/null | grep -E "^(Name|State|IP|Uptime)" || true
    exit 0
  fi
  sleep 1
done

echo "VM did not reach running state within 30s."
prlctl status "${VM_NAME}"
exit 1
