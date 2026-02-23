#!/usr/bin/env bash
set -euo pipefail

# Thin wrapper to keep OpenClaw workspace commands short and stable.
# All dispatch logic lives in Cortex core at integrations/openclaw_agi_dispatch.py.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
DISPATCHER="$ROOT_DIR/integrations/openclaw_agi_dispatch.py"

if [[ ! -f "$DISPATCHER" ]]; then
  echo "error: dispatcher not found: $DISPATCHER"
  exit 1
fi

exec python3 "$DISPATCHER" "$@"
