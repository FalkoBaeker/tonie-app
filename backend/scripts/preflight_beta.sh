#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[preflight] check: listeners on :8787"
if command -v lsof >/dev/null 2>&1; then
  listeners="$(lsof -nP -iTCP:8787 -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$listeners" ]]; then
    echo "WARN multiple/active listeners may exist on :8787"
    echo "$listeners"
  else
    echo "OK no listener conflict detected"
  fi
else
  echo "SKIP lsof not available"
fi

echo "[preflight] check: backend_status.sh"
if ./scripts/backend_status.sh; then
  echo "OK backend_status"
else
  echo "FAIL backend_status"
  exit 1
fi

echo "[preflight] check: backend_smoke.sh"
if ./scripts/backend_smoke.sh; then
  echo "OK backend_smoke"
else
  echo "FAIL backend_smoke"
  exit 1
fi

echo "PREFLIGHT_OK"
