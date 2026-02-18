#!/usr/bin/env bash
set -euo pipefail

# Starts the Cortex runner VM in the background with:
# - VNC: 127.0.0.1:5905
# - SSH forward: 127.0.0.1:2222 -> guest:22
# The guest disk is the cloned ARM Kali image in ~/VirtualBox VMs/Cortex Runner ARM.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VM_WORKDIR="${ROOT_DIR}/.vm/cortex-runner-qemu"
PID_FILE="${VM_WORKDIR}/qemu.pid"
MONITOR_SOCK="${VM_WORKDIR}/monitor.sock"
VARS_FILE="${VM_WORKDIR}/edk2-arm-vars.fd"

QEMU_BIN="${QEMU_BIN:-qemu-system-aarch64}"
QEMU_SHARE="${QEMU_SHARE:-/opt/homebrew/Cellar/qemu/10.1.3/share/qemu}"
FIRMWARE_CODE="${QEMU_FIRMWARE_CODE:-${QEMU_SHARE}/edk2-aarch64-code.fd}"
FIRMWARE_VARS_TEMPLATE="${QEMU_FIRMWARE_VARS_TEMPLATE:-${QEMU_SHARE}/edk2-arm-vars.fd}"
DISK_FILE="${CORTEX_VM_DISK:-$HOME/VirtualBox VMs/Cortex Runner ARM/Cortex Runner ARM.vdi}"

VNC_BIND="${CORTEX_VM_VNC_BIND:-127.0.0.1:5}"
SSH_FWD="${CORTEX_VM_SSH_FWD:-tcp:127.0.0.1:2222-:22}"
MEMORY_MB="${CORTEX_VM_MEMORY_MB:-8192}"
CPUS="${CORTEX_VM_CPUS:-6}"

mkdir -p "${VM_WORKDIR}"

if [[ -f "${PID_FILE}" ]]; then
  old_pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
  if [[ -n "${old_pid}" ]] && ps -p "${old_pid}" >/dev/null 2>&1; then
    echo "VM already running (pid=${old_pid})"
    echo "VNC:  vnc://127.0.0.1:5905"
    echo "SSH:  ssh -p 2222 <guest_user>@127.0.0.1"
    exit 0
  fi
  rm -f "${PID_FILE}"
fi

if [[ ! -f "${DISK_FILE}" ]]; then
  echo "Missing disk image: ${DISK_FILE}"
  echo "Set CORTEX_VM_DISK to a valid .vdi or .qcow2 path and retry."
  exit 1
fi

disk_ext="${DISK_FILE##*.}"
disk_ext_lc="$(printf '%s' "${disk_ext}" | tr '[:upper:]' '[:lower:]')"
case "${disk_ext_lc}" in
  vdi) DISK_FORMAT="${CORTEX_VM_DISK_FORMAT:-vdi}" ;;
  qcow2) DISK_FORMAT="${CORTEX_VM_DISK_FORMAT:-qcow2}" ;;
  raw|img) DISK_FORMAT="${CORTEX_VM_DISK_FORMAT:-raw}" ;;
  *) DISK_FORMAT="${CORTEX_VM_DISK_FORMAT:-vdi}" ;;
esac

if [[ ! -f "${FIRMWARE_CODE}" ]]; then
  echo "Missing firmware code file: ${FIRMWARE_CODE}"
  exit 1
fi

if [[ ! -f "${VARS_FILE}" ]]; then
  if [[ ! -f "${FIRMWARE_VARS_TEMPLATE}" ]]; then
    echo "Missing firmware vars template: ${FIRMWARE_VARS_TEMPLATE}"
    exit 1
  fi
  cp -f "${FIRMWARE_VARS_TEMPLATE}" "${VARS_FILE}"
fi

rm -f "${MONITOR_SOCK}"

"${QEMU_BIN}" \
  -machine virt,accel=hvf,highmem=on \
  -cpu host \
  -smp "${CPUS}" \
  -m "${MEMORY_MB}" \
  -device virtio-gpu-pci \
  -display none \
  -vnc "${VNC_BIND}" \
  -device qemu-xhci \
  -device usb-kbd \
  -device usb-tablet \
  -nic "user,hostfwd=${SSH_FWD}" \
  -drive "if=pflash,format=raw,readonly=on,file=${FIRMWARE_CODE}" \
  -drive "if=pflash,format=raw,file=${VARS_FILE}" \
  -drive "if=virtio,format=${DISK_FORMAT},file=${DISK_FILE}" \
  -daemonize \
  -pidfile "${PID_FILE}" \
  -monitor "unix:${MONITOR_SOCK},server,nowait"

pid="$(cat "${PID_FILE}")"
echo "VM started (pid=${pid})"
echo "VNC:  vnc://127.0.0.1:5905"
echo "SSH:  ssh -p 2222 <guest_user>@127.0.0.1"
