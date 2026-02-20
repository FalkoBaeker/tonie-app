# S7-06 — eBay API Spike + Integrationsplan

## Typ
Should (strategisch wichtig)

## Ziel
Bewerten und vorbereiten, wie eBay Developer API robust in die Pricing-Pipeline integriert wird.

## Scope
- Endpoint-/Quota-/Auth-Analyse der eBay API
- Mapping auf bestehende Pricing-Modelle
- Fallback-Strategie (API-Limit/Fehler)
- Aufwandsschätzung für produktive Integration

## Out of Scope
- Vollständige Migration aller Datenquellen in diesem Ticket

## Akzeptanzkriterien
- Entscheidungsdokument mit Go/No-Go.
- Risikoanalyse zu Rate Limits und Datenabdeckung.
- Konkreter Umsetzungsplan für S8.

## DoD
- `docs/architecture/ebay-api-integration-plan.md` erstellt.
- Schnittstellenentwurf (Adapter/Normalizer) beschrieben.
- Falls möglich: minimaler Prototyp-Call mit Beispielantwort dokumentiert.

## Testfälle
1. Auth gegen eBay API erfolgreich (Test-Creds).
2. Beispielquery liefert auswertbare Daten.
3. Ausfall/Limits -> Fallback-Pfad nachvollziehbar.

## Risiken
- Rate Limits/Terms schränken Abdeckung ein.
- Datenmodellabweichungen erfordern aufwendiges Normalizing.

## Artefakte
- Integrationsplan + Aufwand (S/M/L)
- Risiko- und Migrationsmatrix
