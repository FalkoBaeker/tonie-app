# S7-01 — Legal & GDPR Basis

## Typ
Blocker

## Ziel
Rechtliche Mindestanforderungen für EU/DE-Release sauber herstellen.

## Scope
- Privacy Policy (Datenerhebung, Zwecke, Speicherfristen, Rechte)
- TOS/AGB (Leistungsumfang, Haftung/Disclaimer)
- Support URL + Support-Kontakt
- In-App Verlinkung (Account/Settings)
- GDPR/DSGVO Kurzsektion in App (Auskunft, Löschung, Korrektur)

## Out of Scope
- Vollständige juristische Einzelfallberatung
- Unternehmensweite DPA/AVV-Verhandlung

## Akzeptanzkriterien
- Dokumente sind versioniert und in Build-Umgebung verlinkbar.
- In-App Links öffnen die richtigen Zielseiten.
- Texte widersprechen dem tatsächlichen Datenfluss nicht.
- Support-Kanal ist erreichbar.

## DoD
- `docs/legal/privacy-policy.md` vorhanden.
- `docs/legal/terms-of-service.md` (oder AGB) vorhanden.
- Support-URL in App-Konfiguration hinterlegt.
- QA-Checkliste „Legal links reachable“ grün.
- Owner-Review/Freigabe dokumentiert.

## Testfälle
1. App starten -> Account/Settings -> Privacy/TOS öffnen.
2. Offline-Fall: sinnvolle Fehlermeldung bei nicht erreichbarer URL.
3. Konsistenzcheck: genannte Datenkategorien vs. echte App-Funktion.

## Risiken
- Rechtstexte unvollständig oder technisch inkonsistent.

## Artefakte
- `docs/legal/*`
- PR mit Screenshot der In-App Links
