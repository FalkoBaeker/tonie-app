#!/usr/bin/env bash
set -euo pipefail

TARGET="$HOME/Library/LaunchAgents/com.falko.toniefinder.backend.plist"

launchctl bootout "gui/$(id -u)/com.falko.toniefinder.backend" >/dev/null 2>&1 || true
rm -f "$TARGET"

echo "removed: $TARGET"
