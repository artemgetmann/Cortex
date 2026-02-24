#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
  echo "error: TELEGRAM_BOT_TOKEN is required"
  echo "hint: export TELEGRAM_BOT_TOKEN='123456:abc...'"
  exit 2
fi

if [[ -z "${TELEGRAM_ALLOWED_USERS:-}" ]]; then
  echo "warning: TELEGRAM_ALLOWED_USERS is empty (all users can message this bot token)"
fi

exec python3 "$ROOT_DIR/integrations/telegram_cortex_gateway.py"
