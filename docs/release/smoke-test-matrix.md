# Smoke Test Matrix (RC)

Stand: 2026-02-20

## Umgebung
- Device: __________________
- iOS Version: _____________
- Build: ___________________
- Backend URL: _____________
- Auth Mode: _______________

## Statuslegende
- PASS / FAIL / BLOCKED / N/A

| Bereich | Testfall | Preconditions | Steps | Expected Result | Status | Notes |
|---|---|---|---|---|---|---|
| Auth | Login erfolgreich | verifizierter User vorhanden | App öffnen -> Login | Login klappt, Main Tabs sichtbar |  |  |
| Auth | Register + Verify Hinweis | neuer User / verify required | Register ausführen | Hinweis "Bitte E-Mail bestätigen und danach einloggen." sichtbar |  |  |
| Auth | Falsches Passwort | bestehender User | falsches Passwort eingeben | Verständliche Fehlermeldung, kein Crash |  |  |
| Resolve/Pricing | Suche + Auswahl | eingeloggt oder lokaler Modus | Query eingeben -> Treffer wählen | Preise laden inkl. Qualität/Freshness |  |  |
| Pricing | Manueller Preis-Refresh | ausgewählter Treffer mit Preis | "Preis aktualisieren" drücken | Loading sichtbar, danach Aktualisierungsinfo |  |  |
| Watchlist | Add Item | eingeloggt | In Pricing "Zur Watchlist hinzufügen" | Item erscheint in Watchlist |  |  |
| Watchlist | Remove Item | Watchlist enthält Item | Swipe Delete | Item wird entfernt, kein Fehler |  |  |
| Watchlist | Refresh | eingeloggt + Items vorhanden | "Preise aktualisieren" oder Pull-to-refresh | Preise/Freshness werden aktualisiert |  |  |
| Alerts | Filter Alle/Neu | Alerts vorhanden | Zwischen Alle/Neu wechseln | Liste/Empty State korrekt |  |  |
| Alerts | Typ: Preis unter Zielpreis | passender Datenfall | Alert laden | Label "Preis unter Zielpreis" + Begründung sichtbar |  |  |
| Alerts | Typ: Preisabfall über Schwellwert | passender Datenfall | Alert laden | Label "Preisabfall über Schwellwert" + Begründung sichtbar |  |  |
| Account/Legal | Legal Links | URLs gesetzt | Account öffnen -> Links öffnen | Privacy/TOS/Support öffnen korrekt |  |  |
| Account | DSGVO Hinweis | keine | Account öffnen | DSGVO-Hinweis sichtbar |  |  |

## Zusammenfassung
- Passed: ___
- Failed: ___
- Blocked: ___
- Go/No-Go Empfehlung: ___
