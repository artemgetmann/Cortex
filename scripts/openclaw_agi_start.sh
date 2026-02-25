#!/usr/bin/env bash
set -euo pipefail

# Start OpenClaw with the isolated AGI runtime profile.
# This wrapper ensures we never accidentally boot against ~/.openclaw.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_STATE_DIR="$HOME/.cloudcode-telegrambot-cortex-agi"
LEGACY_STATE_DIR="$HOME/.openclaw-agi"
if [[ -n "${OPENCLAW_STATE_DIR:-}" ]]; then
  export OPENCLAW_STATE_DIR
elif [[ -d "$LEGACY_STATE_DIR" && ! -d "$DEFAULT_STATE_DIR" ]]; then
  export OPENCLAW_STATE_DIR="$LEGACY_STATE_DIR"
else
  export OPENCLAW_STATE_DIR="$DEFAULT_STATE_DIR"
fi
export OPENCLAW_CONFIG_PATH="${OPENCLAW_CONFIG_PATH:-$OPENCLAW_STATE_DIR/openclaw.json}"

if ! command -v openclaw >/dev/null 2>&1; then
  echo "error: openclaw CLI not found in PATH"
  exit 1
fi

if [[ ! -f "$OPENCLAW_CONFIG_PATH" ]]; then
  echo "AGI config missing at $OPENCLAW_CONFIG_PATH"
  echo "Running setup first..."
  "$ROOT_DIR/scripts/openclaw_agi_setup.sh"
fi

echo "Starting OpenClaw AGI profile:"
echo "  OPENCLAW_STATE_DIR=$OPENCLAW_STATE_DIR"
echo "  OPENCLAW_CONFIG_PATH=$OPENCLAW_CONFIG_PATH"
exec openclaw gateway "$@"
