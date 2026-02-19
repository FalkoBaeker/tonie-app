# Auth + Backend Migration Plan (S4n)

## Phase A — Cloud-ready foundation

Deliverables:
- backend supports env-driven auth mode (`AUTH_MODE`)
- cloud env vars documented (`AUTH_ISSUER`, `AUTH_AUDIENCE`, `AUTH_JWKS_URL`)
- deployment checklist for Render/Railway + managed Postgres target

DoD:
- backend boots with `AUTH_MODE=local` and `AUTH_MODE=external`
- health endpoint remains available
- no regressions in existing tests

Risks:
- misconfigured env secrets in cloud

Rollback:
- set `AUTH_MODE=local`

Success metric:
- CI/tests green + local boot in both modes

---

## Phase B — Managed Auth integration

Deliverables:
- Supabase project configured with Email Verification enabled
- Google OAuth provider configured in Supabase Auth
- backend validates Supabase JWT via JWKS

DoD:
- external token accepted for protected endpoints
- unverified email rejected when required

Risks:
- issuer/audience mismatch
- clock skew/token-expiry confusion

Rollback:
- switch back to `AUTH_MODE=local`

Success metric:
- `/api/auth/me` succeeds with valid external token and fails with invalid/unverified token

---

## Phase C — iOS auth flow migration

Deliverables:
- iOS obtains provider token (email+password or Google via provider SDK)
- iOS sends Bearer JWT to backend
- local-only login UI either hidden behind debug flag or marked dev-only

DoD:
- real sign-in path works end-to-end against deployed backend

Risks:
- token refresh edge cases

Rollback:
- keep local auth mode in dev builds

Success metric:
- device smoke: login -> me -> resolve -> pricing -> watchlist

---

## Phase D — Legacy local-auth retirement

Deliverables:
- local password/session auth removed from prod path
- migration note and cleanup checklist complete

DoD:
- production environment uses external auth only
- no dependency on local session tokens in production path

Risks:
- old clients still using local login

Rollback:
- temporary dual-mode with strict deprecation window

Success metric:
- all active beta users authenticate via managed auth only

---

## Cost-first hosting note

- Recommended first target: **Render or Railway** (pick the cheaper usable plan/free tier at decision time).
- DB target: **managed Postgres free tier** (Supabase or Neon).
- Avoid Vercel as primary API host for this FastAPI backend pattern.

## Data-quality roadmap note

- eBay Developer API is approved and can be used in a later phase for better market-data quality.
- Keep this out of auth migration scope; add as separate follow-up ticket after auth/deploy baseline is stable.
