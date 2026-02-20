# Ops Quality Report (S8-07)

Stand: 2026-02-20

## Ziel
Schneller operativer Überblick über:
- Cache/Freshness
- Fallback-Quote
- Coverage-Lücken
- Letzten Refresh-Run

## Report-Command

```bash
cd backend
source .venv/bin/activate
python scripts/ops_quality_report.py --fresh-minutes 10080 --quality-hours 168 --pretty
```

## Was der Report liefert
- `refresh_policy_minutes`
- `cache_status` (gesamt + fresh window)
- `quality_status` (Fallback Rate, Sample/Latency, Top Fallback IDs)
- `coverage_summary` (Coverage Rate, Top Gaps)
- `latest_refresh_run`

## Weekly Betriebsroutine (empfohlen)
1. Report 1x pro Woche laufen lassen.
2. Bei hoher `fallback_rate` (>20%) zuerst Coverage-Lücken prüfen.
3. Bei sinkender `coverage_rate` Refresh-Run priorisieren.
4. Erst danach Gewichte (`MARKET_SOURCE_WEIGHTS`) feinjustieren.

## Eskalationsregeln
- `fallback_rate > 30%` -> sofortige Analyse + zusätzlicher Refresh-Run.
- `coverage_rate < 70%` im 7-Tage-Fenster -> Backlog auf Datenabdeckung priorisieren.
- Keine API-Verfügbarkeit (eBay) -> Scrape-Fallback aktiv lassen, kein Hard-Fail.
