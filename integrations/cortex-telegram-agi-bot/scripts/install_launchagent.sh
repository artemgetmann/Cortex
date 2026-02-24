#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$HOME/Library/LaunchAgents/com.cortex-telegram-agi.plist"
LABEL="com.cortex-telegram-agi"
SHELL_BIN="${SHELL_BIN:-/opt/homebrew/bin/zsh}"

if [[ ! -f "$ROOT_DIR/.env" ]]; then
  echo "error: missing $ROOT_DIR/.env"
  echo "Create .env first. Aborting."
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"
cat >"$TARGET" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${SHELL_BIN}</string>
    <string>-lc</string>
    <string>cd ${ROOT_DIR} &amp;&amp; ./scripts/start_agi_bot.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT_DIR}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>${HOME}/.bun/bin:${HOME}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/tmp/cortex-telegram-agi.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/cortex-telegram-agi.err</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"
launchctl kickstart -k "gui/$(id -u)/$LABEL"

echo "Installed and started $LABEL"
echo "Logs:"
echo "  /tmp/cortex-telegram-agi.log"
echo "  /tmp/cortex-telegram-agi.err"
