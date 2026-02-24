#!/usr/bin/env bash
set -euo pipefail

LABEL="com.cortex-telegram-agi"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$PLIST"

echo "Stopped and removed $LABEL"
