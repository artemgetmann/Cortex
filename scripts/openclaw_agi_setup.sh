#!/usr/bin/env bash
set -euo pipefail

# This script creates an isolated OpenClaw runtime for AGI testing.
# It never edits ~/.openclaw in-place. Existing bot state stays untouched.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_STATE="${OPENCLAW_SOURCE_STATE:-$HOME/.openclaw}"
DEFAULT_TARGET_STATE="$HOME/.cloudcode-telegrambot-cortex-agi"
LEGACY_TARGET_STATE="$HOME/.openclaw-agi"
if [[ -n "${OPENCLAW_TARGET_STATE:-}" ]]; then
  TARGET_STATE="$OPENCLAW_TARGET_STATE"
elif [[ -d "$LEGACY_TARGET_STATE" && ! -d "$DEFAULT_TARGET_STATE" ]]; then
  # Backward-compatible default for existing installs.
  TARGET_STATE="$LEGACY_TARGET_STATE"
else
  TARGET_STATE="$DEFAULT_TARGET_STATE"
fi
WORKSPACE_DIR="${OPENCLAW_AGI_WORKSPACE:-$ROOT_DIR/integrations/openclaw-agi/workspace}"
TARGET_CONFIG="${OPENCLAW_TARGET_CONFIG:-$TARGET_STATE/openclaw.json}"
TARGET_PORT="${OPENCLAW_AGI_PORT:-18889}"
TELEGRAM_TOKEN="${OPENCLAW_AGI_TELEGRAM_BOT_TOKEN:-}"
ALLOW_FROM="${OPENCLAW_AGI_ALLOW_FROM:-}"

SOURCE_CONFIG="${SOURCE_STATE}/openclaw.json"
SOURCE_OAUTH="${SOURCE_STATE}/credentials/oauth.json"
TARGET_OAUTH="${TARGET_STATE}/credentials/oauth.json"
SOURCE_ENV="${SOURCE_STATE}/.env"
TARGET_ENV="${TARGET_STATE}/.env"

if [[ ! -f "$SOURCE_CONFIG" ]]; then
  echo "error: source config not found at $SOURCE_CONFIG"
  exit 1
fi

# Create isolated state + workspace paths first, then write config.
mkdir -p "$TARGET_STATE" "$TARGET_STATE/credentials" "$TARGET_STATE/logs" "$WORKSPACE_DIR" "$WORKSPACE_DIR/bin"

# Copy OAuth once so the AGI runtime can reuse provider auth without re-login.
# This is a one-time copy into isolated state, not a symlink back to ~/.openclaw.
if [[ -f "$SOURCE_OAUTH" && ! -f "$TARGET_OAUTH" ]]; then
  cp "$SOURCE_OAUTH" "$TARGET_OAUTH"
  chmod 600 "$TARGET_OAUTH" || true
fi

# Copy .env once for provider keys used by gateway plugins/tools.
if [[ -f "$SOURCE_ENV" && ! -f "$TARGET_ENV" ]]; then
  cp "$SOURCE_ENV" "$TARGET_ENV"
  chmod 600 "$TARGET_ENV" || true
fi

export SOURCE_CONFIG TARGET_CONFIG WORKSPACE_DIR TARGET_PORT TELEGRAM_TOKEN ALLOW_FROM
python3 - <<'PY'
import json
import os
import secrets
from pathlib import Path

source = Path(os.environ["SOURCE_CONFIG"])
target = Path(os.environ["TARGET_CONFIG"])
workspace = os.environ["WORKSPACE_DIR"]
port = int(os.environ["TARGET_PORT"])
telegram_token = os.environ.get("TELEGRAM_TOKEN", "").strip()
allow_from_raw = os.environ.get("ALLOW_FROM", "").strip()

cfg = json.loads(source.read_text(encoding="utf-8"))

# Keep most existing config so auth/provider wiring still works, but force
# AGI-specific isolation knobs.
agents = cfg.setdefault("agents", {})
defaults = agents.setdefault("defaults", {})
defaults["workspace"] = workspace

gateway = cfg.setdefault("gateway", {})
gateway["port"] = port
gateway_auth = gateway.setdefault("auth", {})
if not isinstance(gateway_auth, dict):
    gateway_auth = {"mode": "token"}
gateway_auth.setdefault("mode", "token")
if not gateway_auth.get("token"):
    gateway_auth["token"] = secrets.token_hex(24)
gateway["auth"] = gateway_auth

# Keep AGI profile focused on Telegram only. This avoids inherited channel
# config drift (e.g., WhatsApp auto-enable mutations) from the primary profile.
channels = cfg.get("channels", {})
telegram = channels.get("telegram", {}) if isinstance(channels, dict) else {}

# Safety default: disable Telegram until a dedicated bot token is provided.
# This prevents accidental dual-login conflict with the existing live bot.
if telegram_token:
    telegram["enabled"] = True
    telegram["botToken"] = telegram_token
else:
    telegram["enabled"] = False
    telegram["botToken"] = ""

if allow_from_raw:
    allow_values = [item.strip() for item in allow_from_raw.split(",") if item.strip()]
    if allow_values:
        telegram["allowFrom"] = allow_values

cfg["channels"] = {"telegram": telegram}

# Isolated AGI profile should not inherit plugin entries that may not exist
# under the new state dir. This avoids startup validation failures.
plugins = cfg.setdefault("plugins", {})
plugins["entries"] = {}
cfg["plugins"] = plugins

target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(cfg, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
PY

echo "AGI runtime prepared."
echo "  state:     $TARGET_STATE"
echo "  config:    $TARGET_CONFIG"
echo "  workspace: $WORKSPACE_DIR"
echo "  port:      $TARGET_PORT"
if [[ -n "$TELEGRAM_TOKEN" ]]; then
  echo "  telegram:  enabled (dedicated token set)"
else
  echo "  telegram:  disabled (set OPENCLAW_AGI_TELEGRAM_BOT_TOKEN and rerun setup)"
fi
