# S5 Runbook — Supabase External Auth in Staging (cost-first)

This runbook activates external auth in staging with minimal cost.

## Recommended free-tier path

- Auth: Supabase Auth (free tier)
- API host: Render free web service (or Railway if cheaper at execution time)
- DB: keep SQLite for initial staging, migrate to managed Postgres as next hardening step

## 1) Supabase project setup

1. Create a Supabase project (free tier).
2. In **Authentication -> Providers**:
   - enable Email
   - set **Confirm email** = ON
3. (Optional) enable Google provider if client credentials are ready.

Collect values:
- Project URL: `https://<project-ref>.supabase.co`
- JWT issuer: usually project URL
- JWKS URL: `https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json`
- Audience: `authenticated` (default for Supabase access tokens)

## 2) Deploy staging backend (Render)

Use `backend/render.yaml` or manual setup with:
- root dir: `backend`
- build command: `pip install -r requirements.txt`
- start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Set env vars in Render:
- `ENVIRONMENT=staging`
- `DEBUG=false`
- `AUTH_MODE=external`
- `AUTH_REQUIRE_VERIFIED_EMAIL=true`
- `AUTH_JWKS_URL=<supabase-jwks-url>`
- `AUTH_ISSUER=<supabase-project-url>`
- `AUTH_AUDIENCE=authenticated`

## 3) Staging E2E verification

### Verified user happy path

1. Sign up user via Supabase Auth (email+password)
2. Verify email via mailbox link
3. Obtain access token from Supabase session
4. Run:

```bash
cd backend
STAGING_API_BASE_URL='https://<staging-host>/api' \
STAGING_BEARER_TOKEN='<supabase-access-token>' \
./scripts/staging_external_auth_check.sh
```

Expected output:
- `STAGING_EXTERNAL_AUTH_OK ...`

### Unverified email negative case

Call protected endpoint with token from unverified user:
- expected: HTTP `401` with `email not verified`

## 4) Rollback

If staging auth is broken:
- set `AUTH_MODE=local`
- restart service

## 5) Secrets hygiene

- Never commit Supabase keys/secrets into repo
- Store secrets only in hosting provider env settings
- Rotate keys if leaked

## 6) Cost note

- Supabase Auth + Render free tier are usually enough for early beta.
- Paid upgrade is typically needed only when uptime/usage grows.
