# Source Weight Calibration (Initial, S8-06)

Stand: 2026-02-20

## Ziel
Sinnvolle Startgewichte für multi-source Pricing festlegen, ohne früh zu overfitten.

## Initiale Gewichte

| Source | Weight | Begründung |
|---|---:|---|
| `ebay_sold` | 1.00 | Primäre sold/completed Referenz |
| `ebay_api_sold` | 1.00 | Für künftige echte sold API Feeds |
| `ebay_api_listing` | 0.80 | Gute API-Qualität, aber oft Angebots- statt Abschlussdaten |
| `kleinanzeigen_listing` | 0.35 | Angebotsdaten, höhere Verhandlungsspanne |
| `kleinanzeigen_offer` | 0.35 | Analog Listing-Risiko |
| `kleinanzeigen_sold_estimate` | 0.45 | Modellierte Näherung, nicht echtes sold Ground Truth |

## Guardrails gegen Overfitting
1. Gewichte nur in kleinen Schritten ändern (max ±0.1 pro Iteration).
2. Immer gegen Referenzfälle prüfen (Expert-Review + Verlauf).
3. Wenn Fallback-Quote steigt, keine aggressive API-Gewichtung einführen.
4. Shadow-Mode zuerst beobachten, dann erst `EBAY_API_INCLUDE_IN_PRICING=true`.

## Messkriterien für nächste Kalibrierung
- Median absolute deviation gegen Referenzpreise (internes Set)
- Fallback-Quote (`fallback_no_live_market_data`)
- Anteil `market_live_*` mit ausreichender `effective_sample_size`
- Ausreißerquote (IQR-bereinigt)

## Risiken / Grenzen
- API-Listingpreise können über sold-Werten liegen.
- Dünne Datenlage verzerrt Quantile stärker.
- Ein globales Gewicht passt nicht für jede Produktnische gleich gut.

## Empfehlung
- Initial konservativ bleiben.
- Nach 1–2 Wochen Telemetrie und Expert-Check (Tonie-Realitätscheck) feinjustieren.
