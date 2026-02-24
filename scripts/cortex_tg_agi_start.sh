#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOT_DIR="$ROOT_DIR/integrations/cortex-telegram-agi-bot"

if [[ ! -d "$BOT_DIR" ]]; then
  echo "error: missing bot dir $BOT_DIR"
  exit 1
fi

exec "$BOT_DIR/scripts/start_agi_bot.sh"
