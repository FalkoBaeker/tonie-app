# TestFlight Prep (S7-08)

Stand: 2026-02-20

## 1) Build & Versioning
- [ ] `CFBundleShortVersionString` geprüft (z. B. 1.0.x)
- [ ] `CFBundleVersion` erhöht (Build Nummer)
- [ ] Changelog/Release Notes zum Build passend
- [ ] Build-Konfiguration ist Release (nicht Debug)

## 2) Release Notes Draft (Template)

### What’s New
- Verbesserte Auth UX (klarere Loading/Status-Hinweise)
- Verbesserte Alerts (verständliche Typen + Begründung)
- Preis-Freshness sichtbar in Pricing/Watchlist
- Legal/Support Links im Account-Bereich

### Bug Fixes
- Stabilitäts- und Konsistenzfixes in Auth/Alerts

### Known Limitations
- Fotoerkennung bleibt assistiv (Bestätigung notwendig)
- Preisqualität variiert bei dünner Marktdatenlage

## 3) Known Issues (vor Upload prüfen)
- [ ] Offene Crash-Bugs: keine kritischen
- [ ] Offene Blocker aus RC-Checklist: keine
- [ ] Nicht-blockierende Restpunkte dokumentiert

## 4) Upload- und Verifikations-Checklist
- [ ] Archiv/Build mit korrekter Signing-Konfiguration erzeugt
- [ ] Upload in App Store Connect abgeschlossen
- [ ] Build in TestFlight sichtbar
- [ ] Interne Tester-Gruppe zugewiesen
- [ ] Testhinweise (Smoke-Matrix) an Tester kommuniziert

## 5) Rollback-/Fallback-Plan
- [ ] Letzten stabilen Build-Stand notiert
- [ ] Rollback-Entscheider benannt
- [ ] Kriterium für Hotfix vs Rollback dokumentiert

## 6) Final Sign-off
- Owner:
- QA:
- Datum:
- Build:
- Ergebnis: GO / NO-GO
