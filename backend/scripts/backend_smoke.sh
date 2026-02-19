#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${TF_BACKEND_BASE_URL:-http://127.0.0.1:8787/api}"
QUERY="${TF_SMOKE_QUERY:-hexe}"
PASSWORD="${TF_SMOKE_PASSWORD:-TonieFinder123!}"
RUN_ID="$(date +%Y%m%d%H%M%S)"
EMAIL="smoke_${RUN_ID}@local.test"

json_post() {
  local url="$1"
  local body="$2"
  curl -sS -f -H 'Content-Type: application/json' -X POST "$url" -d "$body"
}

echo "[1/5] health"
./scripts/backend_status.sh >/dev/null

echo "[2/5] register"
register_response="$(json_post "$BASE_URL/auth/register" "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")"
token="$(python3 - <<'PY' "$register_response"
import json
import sys
print(json.loads(sys.argv[1])["token"])
PY
)"

echo "[3/5] me"
curl -sS -f -H "Authorization: Bearer $token" "$BASE_URL/auth/me" >/dev/null

echo "[4/5] resolve"
resolve_response="$(json_post "$BASE_URL/tonies/resolve" "{\"query\":\"$QUERY\"}")"
tonie_id="$(python3 - <<'PY' "$resolve_response"
import json
import sys
payload = json.loads(sys.argv[1])
candidates = payload.get("candidates") or []
if not candidates:
    raise SystemExit("resolve returned no candidates")
print(candidates[0]["tonie_id"])
PY
)"

echo "[5/5] pricing"
curl -sS -f "$BASE_URL/pricing/$tonie_id?condition=good" >/dev/null

echo "SMOKE_OK tonie_id=$tonie_id query=$QUERY"
