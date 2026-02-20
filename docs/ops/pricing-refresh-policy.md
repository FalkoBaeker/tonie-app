# Pricing Refresh Policy (S7-05)

Stand: 2026-02-20

## Ziel
Preise für Nutzer nachvollziehbar aktuell halten und gleichzeitig Last begrenzen.

## Aktueller Mechanismus

### 1) Manueller Refresh in der App
- **Pricing-View:** Button `Preis aktualisieren` lädt den aktuell ausgewählten Tonie neu.
- **Watchlist-View:** Button `Preise aktualisieren` sowie Pull-to-refresh laden `/watchlist?refresh=true`.

### 2) Automatischer Refresh (Backend)
- Ziel-Frequenz: **1x pro Woche** (`MARKET_AUTO_REFRESH_INTERVAL_MINUTES=10080`).
- Aktivierung über Runtime-Env:
  - `MARKET_AUTO_REFRESH_ENABLED=true`
  - `MARKET_AUTO_REFRESH_INTERVAL_MINUTES=10080`
- Begründung: realistischer Markt-Rhythmus bei geringer Last.

### 3) UI-Freshness
- Pricing zeigt: `Zuletzt aktualisiert: <Zeitpunkt>` basierend auf dem Fetch-Zeitpunkt.
- Watchlist zeigt pro Eintrag: `Zuletzt aktualisiert: <updated_at>` (falls vorhanden).
- Bei schwacher Datenlage/stale Quelle wird ein Hinweis angezeigt.

## Stale-Regel (praktisch)
- **Watchlist:** älter als 24h seit `updated_at` => Hinweis „möglicherweise veraltet“.
- **Pricing:** Quellen mit `stale`/`fallback` im Source-Feld werden als potenziell veraltet gekennzeichnet.

## Nutzer-Flow
1. Nutzer öffnet Watchlist oder Pricing.
2. Bei Bedarf manuellen Refresh auslösen.
3. UI zeigt Loading + anschließende Erfolgs-/Fehlerinfo.
4. Freshness-Information direkt in der jeweiligen Ansicht sichtbar.

## Grenzen / Risiken
- Freshness im Pricing basiert aktuell auf App-Fetch-Zeitpunkt; backendseitiger exakter Datenzeitstempel wäre noch präziser.
- Bei dünner Marktdatenlage können Fallback-/stale Quellen trotz Refresh auftreten.
- Häufiges manuelles Refresh erhöht Last; Scheduling/Throttling bleibt relevant für spätere Ausbaustufen.
