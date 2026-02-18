#!/usr/bin/env bash
set -euo pipefail

# Provisions a dedicated VirtualBox VM clone used as the disk source for the
# QEMU runner scripts.

BASE_VM="${CORTEX_VM_BASE:-Kali Linux Mac VM}"
TARGET_VM="${CORTEX_VM_TARGET:-Cortex Runner ARM}"

if ! command -v VBoxManage >/dev/null 2>&1; then
  echo "VBoxManage not found."
  exit 1
fi

if VBoxManage list vms | rg -F "\"${TARGET_VM}\"" >/dev/null 2>&1; then
  echo "VM already exists: ${TARGET_VM}"
else
  echo "Cloning '${BASE_VM}' -> '${TARGET_VM}'..."
  VBoxManage clonevm "${BASE_VM}" --name "${TARGET_VM}" --register
fi

# Keep settings explicit so the clone is reproducible.
VBoxManage modifyvm "${TARGET_VM}" \
  --memory 8192 \
  --cpus 6 \
  --vram 32 \
  --audio none \
  --clipboard disabled \
  --draganddrop disabled \
  --vrde on \
  --vrdeaddress 127.0.0.1 \
  --vrdeport 5000

# Refresh SSH forward rule idempotently.
VBoxManage modifyvm "${TARGET_VM}" --natpf1 delete guestssh >/dev/null 2>&1 || true
VBoxManage modifyvm "${TARGET_VM}" --natpf1 "guestssh,tcp,127.0.0.1,2222,,22"

echo "Provisioned VM: ${TARGET_VM}"
VBoxManage showvminfo "${TARGET_VM}" | rg -n "State|Memory size|Number of CPUs|NIC 1 Rule|VRDE"
