#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VM_WORKDIR="${ROOT_DIR}/.vm/cortex-runner-qemu"
PID_FILE="${VM_WORKDIR}/qemu.pid"
MONITOR_SOCK="${VM_WORKDIR}/monitor.sock"

if [[ ! -f "${PID_FILE}" ]]; then
  echo "VM pid file not found; nothing to stop."
  exit 0
fi

pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
if [[ -z "${pid}" ]]; then
  rm -f "${PID_FILE}"
  echo "Empty pid file removed."
  exit 0
fi

if ! ps -p "${pid}" >/dev/null 2>&1; then
  rm -f "${PID_FILE}"
  echo "VM process already stopped."
  exit 0
fi

# Ask guest for graceful shutdown first; this is safer for disk state.
if [[ -S "${MONITOR_SOCK}" ]]; then
  printf 'system_powerdown\n' | nc -U "${MONITOR_SOCK}" >/dev/null 2>&1 || true
fi

for _ in {1..20}; do
  if ! ps -p "${pid}" >/dev/null 2>&1; then
    rm -f "${PID_FILE}" "${MONITOR_SOCK}"
    echo "VM stopped gracefully."
    exit 0
  fi
  sleep 1
done

kill "${pid}" >/dev/null 2>&1 || true
sleep 1

if ps -p "${pid}" >/dev/null 2>&1; then
  kill -9 "${pid}" >/dev/null 2>&1 || true
fi

rm -f "${PID_FILE}" "${MONITOR_SOCK}"
echo "VM force-stopped."
