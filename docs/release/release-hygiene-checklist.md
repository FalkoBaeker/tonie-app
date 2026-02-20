# Release Hygiene Checklist (S7-02)

## Ziel
Sicherstellen, dass im Release-Build keine Debug-/Diagnose-Elemente sichtbar sind.

## Negativ-Checkliste (darf in Release NICHT sichtbar sein)
- [ ] `Diagnostics (Debug)`-Card
- [ ] `Base URL Source`
- [ ] `Auth Mode Source`
- [ ] `Supabase URL Source`
- [ ] `Auth Config Issue`
- [ ] `Device-Test Hint`
- [ ] `Privacy/Terms/Support ... Source`-Zeilen
- [ ] `Debug Log: on/off`

## Positiv-Checkliste (darf/soll in Release sichtbar sein)
- [ ] Konto-E-Mail (falls eingeloggt)
- [ ] Login-Status (angemeldet/abgemeldet)
- [ ] App Version/Build
- [ ] Rechtliche Links nur, wenn echte URLs konfiguriert sind
- [ ] DSGVO-Hinweis in nutzerfreundlicher Form

## Legal URL Guard
- Platzhalter (`example.com`, `<...>`) werden nicht als klickbare Links angezeigt.
- Wenn keine gültigen Legal/Support-Daten vorhanden sind, erscheint nur eine freundliche Hinweiszeile.
