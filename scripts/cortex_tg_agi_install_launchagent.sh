#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOT_DIR="$ROOT_DIR/integrations/cortex-telegram-agi-bot"

exec "$BOT_DIR/scripts/install_launchagent.sh"
