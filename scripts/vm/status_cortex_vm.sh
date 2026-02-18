#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VM_WORKDIR="${ROOT_DIR}/.vm/cortex-runner-qemu"
PID_FILE="${VM_WORKDIR}/qemu.pid"
MONITOR_SOCK="${VM_WORKDIR}/monitor.sock"

if [[ ! -f "${PID_FILE}" ]]; then
  echo "status=stopped"
  exit 0
fi

pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
if [[ -z "${pid}" ]] || ! ps -p "${pid}" >/dev/null 2>&1; then
  echo "status=stopped"
  exit 0
fi

echo "status=running pid=${pid}"
echo "vnc=vnc://127.0.0.1:5905"
echo "ssh=ssh -p 2222 <guest_user>@127.0.0.1"

if [[ -S "${MONITOR_SOCK}" ]]; then
  # Not all terminals render monitor output cleanly; trim ANSI escapes.
  printf 'info status\n' \
    | nc -U "${MONITOR_SOCK}" 2>/dev/null \
    | sed -E 's/\x1b\[[0-9;]*[A-Za-z]//g' \
    | rg "^VM status:" || true
fi
