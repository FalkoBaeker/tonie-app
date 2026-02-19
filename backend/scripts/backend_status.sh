#!/usr/bin/env bash
set -euo pipefail

HEALTH_URL="${TF_BACKEND_HEALTH_URL:-http://127.0.0.1:8787/api/health}"
TIMEOUT_SECONDS="${TF_BACKEND_TIMEOUT_SECONDS:-4}"

body_file="$(mktemp)"
trap 'rm -f "$body_file"' EXIT

curl_exit=0
http_code="$(curl -sS -m "$TIMEOUT_SECONDS" -o "$body_file" -w "%{http_code}" "$HEALTH_URL")" || curl_exit=$?

if [[ "$curl_exit" -ne 0 ]]; then
  echo "DOWN http=000 reason=curl_error url=$HEALTH_URL"
  exit 1
fi

python3 - "$http_code" "$body_file" "$HEALTH_URL" <<'PY'
import json
import sys

http_code = sys.argv[1]
body_path = sys.argv[2]
url = sys.argv[3]

payload = {}
try:
    with open(body_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
except Exception:
    payload = {}

if http_code != "200":
    detail = payload.get("detail") if isinstance(payload, dict) else None
    reason = str(detail or "non_200")
    print(f"DOWN http={http_code} reason={reason} url={url}")
    sys.exit(1)

ok = payload.get("ok") if isinstance(payload, dict) else None
db = payload.get("db") if isinstance(payload, dict) else {}
market = payload.get("market_refresh") if isinstance(payload, dict) else {}

if isinstance(db, dict):
    db_state = db.get("status", "unknown")
else:
    db_state = "unknown"

if isinstance(market, dict):
    market_state = market.get("status", "unknown")
else:
    market_state = "unknown"

state = "UP" if ok else "DOWN"
print(f"{state} http=200 ok={str(bool(ok)).lower()} db={db_state} market_refresh={market_state} url={url}")
sys.exit(0 if ok else 1)
PY
