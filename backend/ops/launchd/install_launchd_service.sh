#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
TEMPLATE="$SCRIPT_DIR/com.falko.toniefinder.backend.plist"
TARGET="$HOME/Library/LaunchAgents/com.falko.toniefinder.backend.plist"

if [[ ! -x "$BACKEND_DIR/.venv/bin/python" ]]; then
  echo "missing Python venv at $BACKEND_DIR/.venv/bin/python"
  echo "run: cd $BACKEND_DIR && python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt"
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$BACKEND_DIR/logs"

python3 - "$TEMPLATE" "$TARGET" "$BACKEND_DIR" <<'PY'
from pathlib import Path
import sys

template = Path(sys.argv[1]).read_text(encoding="utf-8")
target = Path(sys.argv[2])
backend_dir = sys.argv[3]
rendered = template.replace("__BACKEND_DIR__", backend_dir)
target.write_text(rendered, encoding="utf-8")
PY

launchctl bootout "gui/$(id -u)/com.falko.toniefinder.backend" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"
launchctl enable "gui/$(id -u)/com.falko.toniefinder.backend"
launchctl kickstart -k "gui/$(id -u)/com.falko.toniefinder.backend"

echo "installed: $TARGET"
launchctl print "gui/$(id -u)/com.falko.toniefinder.backend" | head -n 12
