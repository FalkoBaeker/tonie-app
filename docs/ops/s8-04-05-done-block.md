# S8-04/05 Hard DONE Block

Stand: 2026-02-21 (Europe/Berlin)
Branch: `main`

## Kontext
S8 ist auf `origin/main` gelandet mit:
- `3e033eb` (S8-01)
- `29fd83e` (S8-02)
- `4ef1f23` (S8-03)
- `be4b037` (S8-06)
- `a23f7cc` (S8-07)

Zusätzlich wurde jetzt ein harter Abschlussblock für S8-04/05 ausgeführt.

---

## S8-04 — Shadow-Monitoring

**Status: DONE**

### Nachweis
1. Monitoring-Tooling + Betriebsdoku vorhanden:
   - `backend/scripts/ops_quality_report.py`
   - `docs/ops/ops-quality-report.md`
   - `docs/ops/pricing-refresh-policy.md`
   - Commit: `a23f7cc`

2. Snapshot-Run ausgeführt (Run #1):
   - Artefakt: `docs/ops/s8-shadow-monitoring-snapshot-001.json`
   - Kerndaten aus dem Snapshot:
     - `fallback_rate`: **7.04%**
     - `coverage_rate_percent`: **96.96%**
     - `fresh_tonie_count`: **592**

---

## S8-05 — Benchmark Run #1 + Guardrails in Product

**Status: DONE**

### Guardrails in Product (technisch)
- Source-Priority/Fallback-Signale in Produktpfad:
  - Datei: `backend/app/services/pricing_engine.py`
  - Commit: `4ef1f23`
- Guardrail-Kalibrierung (initiale Leitplanken):
  - Commit: `be4b037`

### Benchmark Run #1 (durchgeführt)
Vergleich für dieselben 8 Tonie-IDs (`tn_001`..`tn_008`):

1. **API-Live-Mode**
   - `EBAY_API_SHADOW_MODE=false`
   - `EBAY_API_INCLUDE_IN_PRICING=true`
   - `MARKET_CACHE_TTL_MINUTES=0`
   - Artefakt: `docs/ops/s8-benchmark-run-001-mode-api.json`

2. **Fallback-Mode (API aus)**
   - `EBAY_API_ENABLED=false`
   - `MARKET_CACHE_TTL_MINUTES=360`
   - Artefakt: `docs/ops/s8-benchmark-run-001-mode-fallback.json`

3. **Zusammenfassung**
   - Artefakt: `docs/ops/s8-benchmark-run-001-summary.json`
   - Ergebnisse:
     - API-Mode mit API-Source (`ebay_api*`): **8/8**
     - Fallback-Mode mit validem Non-API-Preis: **8/8**
     - Ø absolute Fair-Preis-Differenz: **1.81 EUR**
     - Median absolute Fair-Preis-Differenz: **1.08 EUR**

---

## Sicherheits-/Runtime-Hinweis
Temporäre Env-Umschaltungen für den Benchmark wurden zurückgebaut.
Aktiver Default ist wieder:
- `EBAY_API_ENABLED=true`
- `EBAY_API_SHADOW_MODE=true`
- `EBAY_API_INCLUDE_IN_PRICING=false`
- `MARKET_CACHE_TTL_MINUTES=360`

---

## Abschluss
- **S8-04: DONE**
- **S8-05: DONE**

Empfehlung (unverändert): **Foto später** (keine Priorisierung vor stabiler Preis-/Ops-Iteration).
