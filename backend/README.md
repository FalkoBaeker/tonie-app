# Tonie Finder Backend

## Run local
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8787
```

Health:
- `GET http://127.0.0.1:8787/api/health`
  - includes current market-refresh run summary

Current status:
- skeleton API is up
- `/api/tonies/resolve` uses hardened fuzzy matching with ambiguity gate (`resolved` / `needs_confirmation` / `not_found`)
  - exact-id/exact-alias fast-path
  - generic query rejection (`"tonie"` etc.) to avoid false-positive prices
  - token-overlap gating on top of fuzzy score for higher precision
- `/api/pricing/{tonie_id}` uses a cache-first pricing engine:
  - tries fresh cached market listings from SQLite
  - falls back to live dual-source fetch (eBay sold + Kleinanzeigen offers) when cache is stale/empty
  - persists fetched listings back to SQLite
  - computes quantiles Q25/Q50/Q75 + condition factors
  - supports source-weighted blending for multi-source cache data (e.g. classifieds with reduced weight)
  - includes an offer-based estimator (`kleinanzeigen_offer_estimate_v1`) when sold data is missing but offer data is sufficient
  - applies stricter data-quality filters (URL canonicalization, accessory/bundle rejects, IQR outlier trimming)
  - logs per-request pricing telemetry (`pricing_events`) including source/sample_size/latency
  - exposes quality KPIs + low-fresh-coverage alerts via `/api/market/quality-status`
  - falls back only when too little/no usable market data exists
- `/api/tonies/recognize` photo-recognition v1 is now scaffolded:
  - multipart image upload (`image`) + Top-K candidate return
  - fail-safe statuses: `resolved` / `needs_confirmation` / `not_found` / `not_configured`
  - local reference-index pipeline (dHash + mean-color similarity) with no paid external API

Current endpoints:
- `GET /api/health`
- `POST /api/tonies/resolve` (body: `{ "query": "..." }`)
- `GET /api/tonies/recognize-status`
- `POST /api/tonies/recognize` (multipart form field: `image`, optional query: `top_k=3`)
- `GET /api/pricing/{tonie_id}?condition=good`
  - response includes:
    - `sofortverkaufspreis`
    - `fairer_marktpreis`
    - `geduldspreis`
    - `sample_size`
    - `source`
    - `quality_tier`
    - `confidence_band` (`A`/`B`/`C`)
    - `confidence_score`
- `GET /api/market/cache-status` (optional `?tonie_id=...`)
- `GET /api/market/coverage-status` (weighted sample coverage per Tonie)
- `GET /api/market/quality-status` (optional `?hours=24&low_sample_threshold=5&fresh_minutes=360&low_fresh_threshold=5`)
- `GET /api/market/refresh-status`
- `POST /api/market/refresh` (body optional: `limit`, `delay_ms`, `max_items`, `background`)
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `GET /api/watchlist` (optional `?refresh=true` to recompute fair prices)
- `POST /api/watchlist`
- `DELETE /api/watchlist/{item_id}`

Market cache refresh worker:
- one-shot refresh:
  - `python scripts/refresh_market_cache.py --limit 50`
- full catalog refresh:
  - `python scripts/refresh_market_cache.py`

External listing import worker (CSV/JSON/JSONL):
- validate only:
  - `python scripts/import_market_listings.py --file ./imports/kleinanzeigen.csv --default-source kleinanzeigen_offer --dry-run`
- import into SQLite cache:
  - `python scripts/import_market_listings.py --file ./imports/kleinanzeigen.csv --default-source kleinanzeigen_offer`

Photo reference index worker:
- place images under `app/data/tonie_refs/<tonie_id>/...`
- build index JSON:
  - `python scripts/build_photo_reference_index.py`
- check readiness:
  - `GET /api/tonies/recognize-status`

Market refresh API examples:
- start async refresh (background):
  - `POST /api/market/refresh` with `{ "limit": 50, "background": true }`
- poll running status:
  - `GET /api/market/refresh-status`
- run sync refresh (wait for completion):
  - `POST /api/market/refresh` with `{ "limit": 20, "background": false }`
- pricing-quality telemetry (last 24h):
  - `GET /api/market/quality-status?hours=24`
- weighted coverage gap report (fresh window):
  - `GET /api/market/coverage-status?fresh_minutes=360&min_effective_samples=12`

Catalog bootstrap (Germany, large Tonie set):
```bash
cd backend
source .venv/bin/activate

# Build merged catalog from tonies.com DE sitemap + product JSON
# Output: app/data/tonies_catalog.json
python scripts/build_tonies_catalog.py
```

Resolver loading order:
1. `app/data/tonies_catalog.json` (preferred, if present)
2. `app/data/tonies_seed.json` (fallback)

Coverage sprint (refresh + verification):
```bash
cd backend
source .venv/bin/activate

# 1) Target low-coverage IDs first (recommended for large catalogs)
python scripts/refresh_low_coverage.py --batch-size 50 --passes 3 --concurrency 4 --fresh-minutes 360 --min-effective-samples 12 --delay-ms 150 --max-items 80

# Alternative: run until fully covered (can take long)
python scripts/refresh_low_coverage.py --batch-size 50 --until-covered --concurrency 4 --fresh-minutes 360 --min-effective-samples 12 --delay-ms 150 --max-items 80

# 2) (Optional) full sweep of resolver entries (can take long)
python scripts/refresh_market_cache.py --limit 0 --delay-ms 200 --max-items 80

# 3) Start API locally
uvicorn app.main:app --host 127.0.0.1 --port 8787

# 4) In another shell, verify weighted coverage + pricing output
curl 'http://127.0.0.1:8787/api/market/coverage-status?fresh_minutes=360&min_effective_samples=12&limit=200'
curl 'http://127.0.0.1:8787/api/pricing/tn_001?condition=good'

# 5) Generate markdown coverage report for full resolver catalog
python scripts/generate_coverage_report.py --fresh-minutes 360 --min-effective-samples 12
```

Automatic refresh (optional):
- enable in `.env`:
  - `MARKET_AUTO_REFRESH_ENABLED=true`
  - `MARKET_AUTO_REFRESH_INTERVAL_MINUTES=360`
  - `MARKET_AUTO_REFRESH_LIMIT=0`
  - `MARKET_AUTO_REFRESH_DELAY_MS=200`
  - `MARKET_AUTO_REFRESH_MAX_ITEMS=80`

Data-quality tuning (optional):
- `MARKET_PRICE_MIN_EUR=3.0`
- `MARKET_PRICE_MAX_EUR=250.0`
- `MARKET_OUTLIER_IQR_FACTOR=1.8`
- `MARKET_MIN_EFFECTIVE_SAMPLES=5`
- `MARKET_DEFAULT_SOURCE_WEIGHT=1.0`
- `MARKET_SOURCE_WEIGHTS={"ebay_sold":1.0,"kleinanzeigen_offer":0.35}`

Photo-recognition tuning (optional):
- `RECOGNITION_REFERENCE_DIR=./app/data/tonie_refs`
- `RECOGNITION_INDEX_PATH=./app/data/tonie_reference_index.json`
- `RECOGNITION_MIN_SCORE=0.72`
- `RECOGNITION_RESOLVED_SCORE=0.90`
- `RECOGNITION_RESOLVED_GAP=0.06`

Next backend milestones:
1. Keep catalog builder fresh (delta updates + regression checks against tonies.com structure changes)
2. Expand telemetry into alerting dashboards (fallback spikes, per-tonie quality drift)
3. Fill real photo-reference dataset + calibrate recognition thresholds on real captures
4. Harden auth/session handling (token rotation, revoke-all, optional device metadata)
