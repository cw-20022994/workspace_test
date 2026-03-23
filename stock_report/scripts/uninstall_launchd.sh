#!/bin/zsh
set -euo pipefail

LABEL="com.stockreport.daily-refresh"
DEST_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_PLIST="$REPO_ROOT/config/launchd/$LABEL.plist"
INSTALL_MODE_FILE="$REPO_ROOT/reports/logs/.launchd_install_mode"

launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
launchctl bootout "gui/$(id -u)" "$DEST_PLIST" >/dev/null 2>&1 || true
launchctl bootout "gui/$(id -u)" "$SOURCE_PLIST" >/dev/null 2>&1 || true
rm -f "$DEST_PLIST"
rm -f "$INSTALL_MODE_FILE"

echo "Removed LaunchAgent: $DEST_PLIST"
