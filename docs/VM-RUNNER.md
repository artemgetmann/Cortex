# VM Runner

This repository includes two VM backends for running isolated environments on macOS Apple Silicon.

## Parallels Desktop (Recommended)

Parallels provides near-native ARM performance with first-class macOS guest support.

### Scripts

- `scripts/vm/prl_start.sh` — Start VM in headless mode
- `scripts/vm/prl_status.sh` — Check VM status and guest connectivity
- `scripts/vm/prl_stop.sh` — Graceful stop with force-kill fallback

### Quick Start

```bash
# Start headless
./scripts/vm/prl_start.sh

# Check status
./scripts/vm/prl_status.sh

# Stop
./scripts/vm/prl_stop.sh
```

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `CORTEX_PRL_VM` | `Cortex Runner` | VM name in Parallels |

### Prerequisites

- Parallels Desktop 26+ with active trial or license
- VM named "Cortex Runner" created via Parallels GUI or `prlctl`
- `prlctl` CLI (installed automatically with Parallels Desktop)

---

## QEMU on Apple Silicon (Legacy)

Lightweight alternative using QEMU with HVF acceleration. No commercial license needed.

### Scripts

- `scripts/vm/provision_cortex_vm.sh` — Clone a VirtualBox VM as disk source
- `scripts/vm/start_cortex_vm.sh` — Start QEMU daemon
- `scripts/vm/status_cortex_vm.sh` — Check status via QEMU monitor
- `scripts/vm/stop_cortex_vm.sh` — Graceful shutdown with force-kill fallback

### Quick Start

```bash
./scripts/vm/provision_cortex_vm.sh
./scripts/vm/start_cortex_vm.sh
./scripts/vm/status_cortex_vm.sh
open "vnc://127.0.0.1:5905"
```

Stop:

```bash
./scripts/vm/stop_cortex_vm.sh
```

### Default Endpoints

- VNC: `vnc://127.0.0.1:5905`
- SSH forward: `ssh -p 2222 <guest_user>@127.0.0.1`

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `CORTEX_VM_DISK` | `~/VirtualBox VMs/Cortex Runner ARM/Cortex Runner ARM.vdi` | Guest disk path |
| `CORTEX_VM_MEMORY_MB` | `8192` | RAM allocation |
| `CORTEX_VM_CPUS` | `6` | CPU cores |

### Notes

- `provision_cortex_vm.sh` clones from `Kali Linux Mac VM` by default.
  - Override with `CORTEX_VM_BASE` and `CORTEX_VM_TARGET`.

---

## Important Limitation

The FL runtime uses macOS Quartz APIs (`computer_use.py`), which are host-mac specific.
A macOS Parallels guest can run these natively. A Linux guest (QEMU) requires a separate guest-side backend.
