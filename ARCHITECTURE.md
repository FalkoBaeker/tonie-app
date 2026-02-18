# Technische Architektur — Tonie Preis App

## Überblick
- **iOS App**: SwiftUI
- **Backend API**: FastAPI (Python)
- **DB**: PostgreSQL
- **Cache**: Redis
- **Jobs/Scraping**: Worker (Playwright + Requests + Parser)
- **Storage**: S3-kompatibel (Bilder/Referenzen)

## Komponenten

### 1) iOS App
- Auth (Email + Apple Login)
- Suche (Text + Foto)
- Zustandsauswahl
- Preisansicht (3 Preise)
- Watchlist

### 2) API Layer
Endpoints (Beispiele):
- POST /auth/register
- POST /auth/login
- POST /tonies/resolve (Text -> Tonie-ID)
- POST /tonies/recognize (Foto -> Kandidaten)
- GET /pricing/{tonie_id}?condition=...
- GET /watchlist
- POST /watchlist

### 3) Pricing Engine
Pipeline:
1. Daten sammeln (Listings/Sales)
2. Normalisieren (Titel, Zustand, Währung, Preis ohne Versand)
3. Filtern (Bundle/Defekt/Fake/Spam)
4. Matching auf Tonie-ID
5. Quantile berechnen (Q25/Q50/Q75)
6. Frische-/Quellengewichtung

### 4) Matching
#### Text-Matching
- Tokenisierung + fuzzy matching
- Synonym-/Alias-Liste
- Ranking + Ambiguitätsprüfung

#### Foto-Matching (v1 praktikabel)
- Referenzbilder pro Tonie (Katalog)
- Vision Embeddings (Feature-Vektoren)
- ANN Similarity Search
- Top-1 + Top-3 Alternativen
- Unsicherheitsgrenze -> Nutzerentscheidung

## Scraping-Strategie (compliant-first)
- nur öffentlich verfügbare Daten
- rate limits / backoff
- robots/ToS respektieren
- keine Login-Bypässe / keine Captcha-Umgehung

## Datenmodell (minimal)
- users
- tonies (master)
- tonie_aliases
- listings_raw
- listings_normalized
- price_snapshots
- watchlists
- recognition_feedback

## Skalierung
- Worker horizontal skalierbar
- DB-Indexes auf (tonie_id, condition, source, created_at)
- Caching für häufige Preisabfragen
- nightly refresh + on-demand refresh
