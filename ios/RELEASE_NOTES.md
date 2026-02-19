# Tonie Finder – Release Notes (RC Prep)

Version: 0.1.2  
Build: 3

## Scope

TestFlight RC packaging/readiness only. No new product features.

## Highlights

- Release candidate version/build bumped for TestFlight (`0.1.2 (3)`)
- Distribution handoff doc added (`ios/TESTFLIGHT_RC.md`)
- Account diagnostics now show app version/build stamp
- Existing observability + smoke checklist retained

## Known issues (current)

- Local development depends on reachable backend base URL
- On unstable networks, users may still see transient API error states and need retry

## Test focus for RC checks

1. Auth login/logout/session restore
2. Pricing resolve + pricing load + retry on backend error
3. Watchlist add/delete/refresh behavior
4. Alerts list + unread toggle
5. Diagnostics section reflects base URL/session/debug log state + version/build stamp
