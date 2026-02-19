# Tonie Finder – Release Notes (RC Prep)

Version: 0.1.1  
Build: 2

## Scope

Release-readiness only. No new product features.

## Highlights

- Observability hooks for API/non-fatal diagnostics (debug gated)
- Improved backend health reporting with DB readiness
- SQLite backup/restore operational scripts + docs
- MVP freeze cleanup and smoke checklist aligned

## Known issues (current)

- Local development depends on reachable backend base URL
- On unstable networks, users may still see transient API error states and need retry

## Test focus for RC checks

1. Auth login/logout/session restore
2. Pricing resolve + pricing load + retry on backend error
3. Watchlist add/delete/refresh behavior
4. Alerts list + unread toggle
5. Diagnostics section reflects base URL/session/debug log state
