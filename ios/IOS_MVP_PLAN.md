# iOS MVP Plan (lokales Backend zuerst, Deploy später)

## Ziel
iOS-App soll jetzt gegen ein lokal laufendes Backend funktionieren. Später soll nur die Base-URL umgestellt werden (keine großen Code-Änderungen).

## Screens + API Calls

1. **Auth Screen (Login/Register)**
   - `POST /api/auth/login`
   - `POST /api/auth/register`
   - danach Verifikation: `GET /api/auth/me`

2. **Pricing / Search Screen**
   - `POST /api/tonies/resolve`
   - `GET /api/pricing/{tonie_id}?condition=...`
   - optional: `POST /api/tonies/recognize`

3. **Watchlist Screen**
   - `GET /api/watchlist`
   - `GET /api/watchlist?refresh=true`
   - `POST /api/watchlist`
   - `DELETE /api/watchlist/{item_id}`

4. **Alerts Screen**
   - `GET /api/watchlist/alerts`
   - `GET /api/watchlist/alerts?unread_only=true`

5. **Account Screen**
   - `GET /api/auth/me`
   - `POST /api/auth/logout`

## Datenmodelle (iOS)

- `AuthSession { token, user(id,email), expiresAt }`
- `CurrentUser { id, email }`
- `TonieCandidate { tonieId, title, score }`
- `PriceTriple { instant, fair, patience, sampleSize, source, qualityTier, confidenceScore }`
- `WatchItem { id, tonieId, title, condition, lastFairPrice, targetPriceEur? }`
- `WatchlistAlert { id, watchlistItemId, tonieId, title, condition, alertType, message, currentPrice, previousPrice?, targetPrice?, isRead, createdAt }`
- `APIError { statusCode, message, isNetworkError }`

## Error States (pro Screen)

- **Auth**: ungültige Credentials (401), User existiert schon (409), Backend nicht erreichbar
- **Pricing/Search**: kein Match (404), zu wenig Daten (Fallback), Timeout/Offline
- **Watchlist**: unauthorized (401), Eintrag nicht gefunden (404), Refresh-Konflikt (409)
- **Alerts**: unauthorized (401), leere Liste (kein Fehler)
- **Global**: lokale HTTP/ATS Fehlkonfiguration, falsche Base-URL

## Reihenfolge (max 10 Tasks)

1. **Base-URL konfigurierbar machen** (Info.plist/Build Setting, Simulator vs Device) + lokale Netzwerk-Doku.
2. **API-Client + Token-Handling (Keychain) + Login/Register+/me Flow**.
3. Einheitliches Error-Mapping (`APIError`) + User-freundliche States.
4. Watchlist gegen echtes Backend stabilisieren (inkl. pull-to-refresh).
5. Alerts Screen minimal (Liste + unread filter).
6. Pricing/Search cleanup: lokale Fallbacks nur klar markiert.
7. Loading/Retry UX pro Screen verbessern.
8. App-Config für Staging/Prod vorbereiten (nur URL-Switch).
9. Smoke-Test-Checkliste + Debug-Logging-Toggles.
10. Release-Readiness Notizen (Testflight später, noch kein Deploy).
