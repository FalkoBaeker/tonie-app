# ADR 0001: Auth + Backend Target Architecture

Status: Accepted
Date: 2026-02-19

## Context

Current local MVP auth accepts email/password directly against local SQLite user/session tables.
That is fine for local development, but not enough for production behavior:

- no mandatory email verification lifecycle
- no social sign-in (Google)
- local session model is not integrated with a managed identity provider
- SQLite + LAN-only setup is not suitable for internet-facing app usage

## Decision

We adopt a split model:

1. **Identity provider (managed auth): Supabase Auth**
   - Email verification support
   - Google OAuth support
   - Free tier available for early beta

2. **Backend API: FastAPI (existing), cloud-ready runtime**
   - Keep existing FastAPI service and endpoint surface
   - Add `AUTH_MODE=external` to validate provider JWTs (JWKS)

3. **Data store target for cloud: Postgres**
   - SQLite remains local/dev fallback only
   - production/staging should use managed Postgres

## Option review (cost-first)

### Auth providers
- **Supabase Auth** (recommended): free tier, fast setup, email verify + Google, low friction.
- Clerk: strong DX, but free tier constraints may force earlier paid tier depending on usage.
- Auth0: powerful, but typically more expensive quickly.
- Firebase Auth: viable and low-cost at small scale, but introduces stronger Firebase ecosystem coupling.

### Hosting for current FastAPI backend
- **Render / Railway / Fly.io** are better fit than Vercel for this backend shape.
- Vercel is great for frontend/serverless workloads, but current stateful API + DB patterns are not an ideal primary match.

## Consequences

- Short-term complexity increases slightly (local + external auth modes).
- Long-term risk decreases significantly (security/auth correctness delegated to proven provider).
- Migration can happen incrementally without breaking local development.

## Cost stance

- Default to free tiers wherever possible.
- If paid tier becomes unavoidable, choose the lowest-cost option that preserves reliability and security.
