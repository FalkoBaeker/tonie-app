# Release Candidate Checklist (S7-08)

Stand: 2026-02-20
Version: RC-v1

## RC Meta
- [ ] RC-Label/Name gesetzt: `RC-YYYYMMDD-<build>`
- [ ] Verantwortlich (Owner) eingetragen
- [ ] Datum/Uhrzeit (Europe/Berlin) eingetragen
- [ ] Go/No-Go Termin geplant

## 1) Build & Test (Tech)
- [ ] `cd ios && xcodebuild test -scheme TonieFinder -destination 'platform=iOS Simulator,name=iPhone 16 Pro'` grün
- [ ] App startet auf iPhone Device ohne Crash beim Start
- [ ] Login-Flow ohne Deadlock/Spinner-Hänger
- [ ] Resolve -> Pricing lädt reproduzierbar
- [ ] Watchlist Refresh (`?refresh=true`) funktioniert ohne Fehlerdialog
- [ ] Alerts laden ohne API-/Mapping-Fehler

## 2) Release Hygiene
- [ ] Debug-UI in Release nicht sichtbar
- [ ] Keine Source-/Env-Diagnosezeilen in Release sichtbar
- [ ] Keine internen Fehlerdetails (Stack/Raw Payload) in User-UI
- [ ] `docs/release/release-hygiene-checklist.md` vollständig geprüft
- [ ] `docs/release/debug-config-audit.md` geprüft (Flags konsistent)

## 3) Legal & Compliance
- [ ] Datenschutzerklärung verlinkt und erreichbar
- [ ] AGB/TOS verlinkt und erreichbar
- [ ] Support-Link und Support-E-Mail sichtbar/korrekt
- [ ] DSGVO-Hinweis in Account-Screen sichtbar
- [ ] Legal-URLs sind echte URLs (kein `example.com`, keine Platzhalter)

## 4) Produkt-/UX Gates
- [ ] Auth UX: klarer Loading-State + verständliche Meldungen
- [ ] Verifizierungs-Hinweis prominent sichtbar
- [ ] Alerts: Typen verständlich (Zielpreis/Preisabfall)
- [ ] Alerts-Filter `Alle/Neu` korrekt
- [ ] Pricing/Watchlist zeigen Freshness nachvollziehbar an

## 5) Konfigurations-Gates
- [ ] `TF_API_BASE_URL` auf Zielumgebung korrekt
- [ ] `TF_AUTH_MODE` korrekt (`external` vs `local` nach Ziel)
- [ ] Supabase-Konfig vollständig (bei external auth)
- [ ] `TF_PRIVACY_POLICY_URL` / `TF_TERMS_URL` / `TF_SUPPORT_URL` echte Ziel-URLs
- [ ] `TF_SUPPORT_EMAIL` produktiver Kontakt

## 6) Release-Artefakte
- [ ] Smoke-Test-Matrix ausgefüllt: `docs/release/smoke-test-matrix.md`
- [ ] TestFlight-Prep ausgefüllt: `docs/release/testflight-prep.md`
- [ ] Known Issues aktualisiert
- [ ] Release Notes Draft finalisiert

## 7) Go / No-Go Entscheidung

### Ergebnis
- [ ] GO
- [ ] NO-GO

### Offene Risiken (falls NO-GO oder GO mit Risiko)
- Risiko 1:
- Risiko 2:
- Mitigation:

### Sign-off
- Owner:
- QA:
- Datum:
- Commit/Tag:
