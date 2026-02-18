# VM Runner (QEMU on Apple Silicon)

This repository now includes helper scripts to run an isolated ARM VM daemon on macOS:

- `scripts/vm/provision_cortex_vm.sh`
- `scripts/vm/start_cortex_vm.sh`
- `scripts/vm/status_cortex_vm.sh`
- `scripts/vm/stop_cortex_vm.sh`

Default endpoints:

- VNC: `vnc://127.0.0.1:5905`
- SSH forward: `ssh -p 2222 <guest_user>@127.0.0.1`

## Quick Start

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

## Notes

- The default guest disk points to: `~/VirtualBox VMs/Cortex Runner ARM/Cortex Runner ARM.vdi`.
- Override disk path with `CORTEX_VM_DISK=/path/to/disk.vdi`.
- `provision_cortex_vm.sh` clones from `Kali Linux Mac VM` by default.
  - Override base/target names with `CORTEX_VM_BASE` and `CORTEX_VM_TARGET`.
- This runner is for isolation so the host desktop stays usable.

## Important Limitation (Current Codebase)

The current FL runtime in this repo uses macOS Quartz APIs (`computer_use.py`), which are host-mac specific.  
Running FL automation fully inside a Linux guest requires a separate guest-side computer-control backend.
