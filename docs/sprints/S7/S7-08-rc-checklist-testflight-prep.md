# S7-08 — RC-Checklist + TestFlight Prep

## Typ
Blocker

## Ziel
Release Candidate strukturiert prüfen und TestFlight-fähig machen.

## Scope
- RC-Checkliste (Tech, Legal, UX, Support)
- Build-/Versionierungsroutine festlegen
- Smoke-Testmatrix (Kernflüsse)
- Known Issues + Release Notes vorbereiten

## Out of Scope
- Öffentlicher App-Store Launch

## Akzeptanzkriterien
- Vollständiger RC-Durchlauf ist dokumentiert.
- Go/No-Go anhand klarer Kriterien möglich.
- TestFlight-Upload-Vorbereitung vollständig.

## DoD
- `docs/release/rc-checklist.md` vorhanden und abgearbeitet.
- Smoke-Tests mit Ergebnisstatus dokumentiert.
- Changelog/Release Notes Draft vorhanden.
- Offene Risiken mit Owner + Next Action benannt.

## Testfälle
1. End-to-end Kernfluss: Auth -> Search/Resolve -> Pricing -> Watchlist -> Alerts.
2. Legal-Links in App funktionieren.
3. Fehler-/Offline-Fälle zeigen brauchbare UX.

## Risiken
- Späte Überraschungen durch fehlende Checklistenpunkte.

## Artefakte
- RC-Checklist
- Smoke-Testreport
- Release Notes Draft
