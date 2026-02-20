# S7-02 — Release-Hygiene / Debug-Off

## Typ
Blocker

## Ziel
Release-Build ohne Debug-Leaks, interne Diagnosen oder dev-only UI.

## Scope
- Debug-Banner/Debug-Views in Release ausblenden
- Logging auf sensitive Inhalte prüfen
- Build-Config Audit (Debug vs Release)
- Fehlertexte für Endnutzer statt internem Stack/Detail

## Out of Scope
- Vollständige Telemetrie-Neuarchitektur

## Akzeptanzkriterien
- Release-Build zeigt keine Debug-Elemente.
- Keine internen technischen Details in User-UI.
- Build-Settings dokumentiert, wie Debug/Release getrennt werden.

## DoD
- Negativliste „Was nie in Release sichtbar sein darf“ abgearbeitet.
- Mind. 1 Device-/Simulator-Release-Smoke ohne Debug-Leak.
- Dokument `docs/release/release-hygiene-checklist.md` vorhanden.

## Testfälle
1. Release-Build installieren -> alle Hauptscreens auf Debug-UI prüfen.
2. Fehlerfall erzwingen -> nur userfreundliche Message sichtbar.
3. Env/Flag-Switch prüfen -> Debug sichtbar nur in Debug-Konfiguration.

## Risiken
- Versteckte Debug-Pfade bleiben übersehbar.

## Artefakte
- Release-Hygiene-Checkliste
- ggf. Build-Config-Diff
