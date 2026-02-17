#!/usr/bin/env bash
set -euo pipefail

# Backward-compatible alias wrapper.
# Intention:
# - Preserve old demo command references that invoke the legacy path.
# - Ensure legacy and canonical runs execute identical logic/output behavior.
# - Avoid maintaining two divergent demo scripts.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "${ROOT_DIR}"

echo "[compat] run_hackathon_demo_legacy.sh -> run_hackathon_demo.sh"
exec bash tracks/cli_sqlite/scripts/run_hackathon_demo.sh "$@"
