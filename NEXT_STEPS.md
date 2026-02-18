# Nächste Schritte (Start jetzt)

## Phase 1 — Fundament (3–5 Tage)
- [x] Repo initialisieren (iOS + backend + worker)
- [x] DB Schema anlegen (SQLite, Users/Sessions/Watchlist)
- [x] Auth + Grund-API (Register/Login/Logout/Me)
- [x] Tonie-Masterliste (Seed) aufbauen

## Phase 2 — Pricing MVP (5–7 Tage)
- [x] Scraper v1 für eBay sold/completed
- [x] Parser + Normalizer
- [x] Bundle-/Outlier-Filter
- [x] Q25/Q50/Q75 API (inkl. sample_size/source)
- [x] Gewichtete Multi-Source-Preisaggregation (sekundäre Quellen mit reduzierter Weight)
- [x] Market-Cache in SQLite (cache-first Pricing + stale/live fallback)
- [x] Worker-Skript für Cache-Refresh (`scripts/refresh_market_cache.py`)
- [x] Refresh-API + Laufstatus (`/api/market/refresh`, `/api/market/refresh-status`)

## Phase 3 — iOS Flow (5–7 Tage)
- [x] Search + Zustand + Preisanzeige (Backend-Preisaufruf verdrahtet, Fallback lokal)
- [x] Ambiguitätsdialog
- [x] Watchlist (Backend-Persistenz + Login-gebundener Sync + Löschfunktion)
- [x] Watchlist-Preisrefresh (Server `?refresh=true` + iOS-Button/Pull-to-refresh)

## Phase 4 — Fotoerkennung v1 (7–10 Tage)
- [ ] Referenzbild-Katalog (echte Tonie-Fotos pro ID sammeln)
- [x] Fotoerkennungs-API v1 (`/api/tonies/recognize`, `/api/tonies/recognize-status`)
- [x] Top-3 Kandidaten + UI (Fotos aus Galerie in der Preis-View)
- [x] Fallback „nicht eindeutig" (Status: `needs_confirmation` / `not_found` / `not_configured`)
- [ ] Embedding-Pipeline v2 (optional, falls visuelles Hashing nicht reicht)

## Phase 5 — Hardening (5 Tage)
- [x] Monitoring/Logs (Refresh-Run-Logging + Pricing-Telemetrie in SQLite + `/api/market/quality-status`)
- [x] Datenqualität-Checks (Resolver-Härtung + striktere Listing-Filter + Outlier-Cleaning)
- [x] Geplanter Cache-Refresh (Backend Auto-Refresh + Refresh-API)
- [x] Freshness-Metrik-Endpoint (`/api/market/cache-status`)
- [x] Coverage-Gap-Endpoint (`/api/market/coverage-status`, inkl. weighted samples)
- [ ] Beta-Test mit Realfällen

## Offene Owner-Inputs
- [ ] Apple Developer Team/Bundle-ID
- [ ] Branding (Name, App-Icon)
- [ ] finale monetization nach Prototyp
