#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${STAGING_API_BASE_URL:-}"
TOKEN="${STAGING_BEARER_TOKEN:-}"
QUERY="${STAGING_RESOLVE_QUERY:-tn_001}"

if [[ -z "$BASE_URL" ]]; then
  echo "missing STAGING_API_BASE_URL (example: https://toniefinder-backend-staging.onrender.com/api)"
  exit 2
fi

if [[ -z "$TOKEN" ]]; then
  echo "missing STAGING_BEARER_TOKEN (Supabase access token for verified user)"
  exit 2
fi

echo "[1/4] health"
curl -sS -f "$BASE_URL/health" >/dev/null

echo "[2/4] auth me (external jwt)"
curl -sS -f -H "Authorization: Bearer $TOKEN" "$BASE_URL/auth/me" >/dev/null

echo "[3/4] resolve"
resolve_json="$(curl -sS -f -H 'Content-Type: application/json' -X POST "$BASE_URL/tonies/resolve" -d "{\"query\":\"$QUERY\"}")"
tonie_id="$(python3 - <<'PY' "$resolve_json"
import json,sys
p=json.loads(sys.argv[1])
arr=p.get('candidates') or []
if not arr:
    raise SystemExit('resolve returned no candidates')
print(arr[0]['tonie_id'])
PY
)"

echo "[4/4] pricing"
curl -sS -f "$BASE_URL/pricing/$tonie_id?condition=good" >/dev/null

echo "STAGING_EXTERNAL_AUTH_OK base=$BASE_URL tonie_id=$tonie_id"
