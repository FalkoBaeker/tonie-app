# Backend Deployment (cost-first)

## Recommended order

1. Render or Railway (choose cheaper usable tier at runtime)
2. Managed Postgres (Supabase or Neon free tier)
3. `AUTH_MODE=external` with Supabase JWT/JWKS

## Start command

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Minimal env vars

```bash
ENVIRONMENT=prod
DEBUG=false
PORT=8787
AUTH_MODE=external
AUTH_JWKS_URL=<provider-jwks-url>
AUTH_ISSUER=<provider-issuer>
AUTH_AUDIENCE=<provider-audience>
AUTH_REQUIRE_VERIFIED_EMAIL=true
```

Supabase mapping (recommended):
- `AUTH_JWKS_URL=https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json`
- `AUTH_ISSUER=https://<project-ref>.supabase.co`
- `AUTH_AUDIENCE=authenticated`

## Platform comparison (short)

- **Render**: easy FastAPI deploy, free plan exists, can sleep on inactivity.
- **Railway**: similarly easy, simple UX, pricing can start low after free credits.
- **Vercel**: excellent for frontend/serverless but not first choice for current backend shape.

## Procfile

`Procfile` is included for platform compatibility:

```text
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```
