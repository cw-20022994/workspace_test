#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LABEL="com.stockreport.daily-refresh"
SOURCE_PLIST="$REPO_ROOT/config/launchd/$LABEL.plist"
DEST_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
INSTALL_MODE_FILE="$REPO_ROOT/reports/logs/.launchd_install_mode"

mkdir -p "$REPO_ROOT/reports/logs"

if [[ ! -f "$SOURCE_PLIST" ]]; then
  echo "LaunchAgent plist not found: $SOURCE_PLIST" >&2
  exit 1
fi

PLIST_TO_BOOTSTRAP="$SOURCE_PLIST"
INSTALL_MODE="direct"

if [[ -d "$HOME/Library/LaunchAgents" && -w "$HOME/Library/LaunchAgents" ]]; then
  cp "$SOURCE_PLIST" "$DEST_PLIST"
  PLIST_TO_BOOTSTRAP="$DEST_PLIST"
  INSTALL_MODE="copied"
fi

launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
launchctl bootout "gui/$(id -u)" "$DEST_PLIST" >/dev/null 2>&1 || true
launchctl bootout "gui/$(id -u)" "$SOURCE_PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_TO_BOOTSTRAP"
launchctl enable "gui/$(id -u)/$LABEL"

printf '%s\n' "$INSTALL_MODE" > "$INSTALL_MODE_FILE"

echo "Installed LaunchAgent: $PLIST_TO_BOOTSTRAP"
echo "Check status with: launchctl print gui/$(id -u)/$LABEL"
