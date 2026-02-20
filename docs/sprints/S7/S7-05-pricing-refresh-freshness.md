# S7-05 — Preisrefresh & Freshness

## Typ
Must

## Ziel
Preisaktualisierungen zuverlässig, nachvollziehbar und transparent machen.

## Scope
- Refresh-Policy definieren (z. B. scheduled + manuell)
- Watchlist-priorisierte Refresh-Reihenfolge
- Freshness in UI anzeigen (z. B. „zuletzt aktualisiert")
- Qualitäts-/Confidence-Hinweise konsistent darstellen

## Out of Scope
- Vollständige Datenquellen-Neuentwicklung

## Akzeptanzkriterien
- Für jeden relevanten Preis ist Freshness ersichtlich.
- Refresh kann reproduzierbar angestoßen und verifiziert werden.
- Policy ist dokumentiert und operationalisierbar.

## DoD
- Technische Refresh-Policy in `docs/ops/pricing-refresh-policy.md`.
- UI zeigt Timestamp/Freshness im Pricing-Kontext.
- E2E-Test: Preisdaten werden nach Refresh aktualisiert angezeigt.

## Testfälle
1. Manueller Refresh -> UI-Timestamp verändert sich.
2. Stale-Datenfall -> Hinweis sichtbar.
3. Watchlist-Item-Refresh priorisiert gegenüber random Katalogitem.

## Risiken
- Hohe Last bei zu aggressiver Refresh-Frequenz.

## Artefakte
- Refresh-Policy-Dokument
- Testprotokoll mit Zeitstempeln
