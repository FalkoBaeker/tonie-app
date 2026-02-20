# eBay API Integration Plan (S7-06 Spike)

Stand: 2026-02-20
Status: Spike / Entscheidungsdokument

## 1) Ausgangslage (Ist)
Der aktuelle Pricing-Stack nutzt primär:
- cache-first Pricing aus SQLite (`market_listings`)
- Live-Nachladen per HTML-Scrape (`ebay.de sold/completed`) + Kleinanzeigen
- Source-gewichtete Aggregation (Q25/Q50/Q75, effective samples, quality tier)

Konkreter Ist-Pfad im Backend:
- `pricing_engine.py` ruft `fetch_ebay_sold_listings_multi_query(...)` auf
- `market_ingestion.py` enthält public-page Scraping mit 403/429/Bot-Page Handling

Risiko heute:
- Anti-Bot/Rate-Limits auf HTML-Scraping
- Datenqualität und Stabilität schwanken je nach Marktlage

## 2) Zielbild
eBay-Daten über offizielle APIs integrieren, um:
1. Stabilität zu erhöhen
2. Abhängigkeit von HTML-Scraping zu reduzieren
3. nachvollziehbare Quoten-/Fehlersteuerung zu bekommen

## 3) API/Auth/Quota Analyse

### 3.1 Auth
- Bevorzugt: OAuth2 (Application Token / Client Credentials) für serverseitige Calls.
- Secrets nur im Backend (nie in iOS-App).
- Token-Cache mit Ablaufzeit und early-refresh (~5 min vor expiry).

### 3.2 Quota/Rate-Limits
- Harte Limits hängen vom eBay-App-Status/Programmfreischaltung ab.
- Technische Schutzmaßnahmen (unabhängig vom finalen Limit):
  - Request-Budget pro Minute + pro Stunde
  - Retry mit Exponential Backoff bei 429/5xx
  - Circuit Breaker bei anhaltendem Limit- oder Auth-Fehler
  - Fallback auf Cache/sekundäre Quellen

### 3.3 Endpoint-Kandidaten (Integrationsstrategie)
| Bereich | Einsatz im Tonie-Stack | Integrationsstatus |
|---|---|---|
| Buy Browse Search APIs | Angebots-/Preisstichproben als strukturierte Primärdaten | Kandidat für v1-Integration |
| Buy Browse Item Details | Detailanreicherung/Validierung einzelner Treffer | Optional |
| Marketplace-Insights ähnliche Sales-Feeds (falls im Account verfügbar) | Bessere „sold/comparable“ Qualität | Prüfen, accountabhängig |

Hinweis: Exakte Endpunktfreigaben sind account-/programmabhängig und müssen im eBay Developer Dashboard verifiziert werden.

## 4) Mapping auf bestehende Pricing-Pipeline

### 4.1 Ziel: keine große Pipeline-Neuarchitektur
Weiterhin dieselbe Aggregationslogik behalten (Q25/Q50/Q75, Quality, Confidence).
Nur den Daten-Adapter austauschen/ergänzen.

### 4.2 Mapping-Tabelle (konzeptionell)
| Interner Feldbedarf | Quelle heute | Quelle eBay API | Ziel in `market_listings` |
|---|---|---|---|
| `title` | HTML parse | API-Title | `title` |
| `price_eur` | HTML parse | API-Preis | `price_eur` |
| `url` | Listing URL | API-Item URL | `url` |
| `sold_at` (falls verfügbar) | teils aus HTML | API-Zeitstempel (falls verfügbar) | `sold_at` |
| `source` | `ebay_sold` | `ebay_api_*` | `source` |

### 4.3 Quellengewichtung (Vorschlag)
- `ebay_api_sold`: 1.00 (Primär)
- `ebay_api_listing`: 0.80
- `ebay_scrape_sold` (Fallback): 0.70
- `kleinanzeigen_*`: bestehend 0.35–0.45

## 5) Fallback-Strategie (verpflichtend)
Reihenfolge pro Pricing-Request:
1. Frischer Cache
2. eBay API Quelle(n)
3. HTML-Scrape Fallback (nur solange API-Abdeckung nicht ausreicht)
4. Kleinanzeigen/sekundäre Quellen
5. deterministischer Fallback (`fallback_no_live_market_data`)

Bei eBay API Problemen (Auth, 429, 5xx):
- Soft-fail + Telemetrieevent
- Keine harte User-Fehlermeldung, stattdessen degrade auf Cache/Fallback

## 6) Implementierungsplan für S8

### 6.1 Minimaler Integrationsschnitt
- Neuer Adapter: `market_ingestion_ebay_api.py`
- Konfig-Keys ergänzen:
  - `EBAY_CLIENT_ID`
  - `EBAY_CLIENT_SECRET`
  - `EBAY_ENV` (sandbox/prod)
  - `EBAY_API_ENABLED`
- Pricing Engine erweitert um Source-Priorisierung (API vor Scrape)

### 6.2 Telemetrie
- Zusätzliche Felder in Pricing-Events:
  - `ebay_api_calls`
  - `ebay_api_rate_limited`
  - `ebay_api_fallback_used`

### 6.3 Rollout
- Phase 1: shadow mode (API-Daten sammeln, aber Gewicht reduziert)
- Phase 2: API als primär, Scrape als fallback
- Phase 3: Scrape nur noch Notfallpfad

## 7) Go / No-Go Entscheidung

### GO, wenn:
- eBay API Zugriff + ausreichende Quoten auf Prod bestätigt
- Datenabdeckung für Tonie-Queries ausreichend
- Latenz akzeptabel

### NO-GO, wenn:
- Kein stabil nutzbarer API-Zugriff für benötigte Marktdaten
- Quoten zu niedrig für Watchlist/Refresh-Betrieb
- Datenqualität schlechter als aktueller Mix

## 8) Aufwandsschätzung (S8)
- Adapter + Auth + Config: **M**
- Engine-Integration + Fallback + Telemetrie: **M**
- QA/Calibration (Gewichte, Qualität): **M**

Gesamt: **M–L (ca. 4–7 Arbeitstage)**

## 9) Empfehlung
**Go mit kontrollierter Einführung** (Shadow -> Primary) statt Big-Bang.
Damit bleibt Pricing stabil, während API-Abdeckung real gemessen wird.
