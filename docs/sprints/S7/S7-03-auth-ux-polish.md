# S7-03 — Auth UX Polish

## Typ
Must

## Ziel
Login/Register-Flow klar, hochwertig und verständlich machen.

## Scope
- Sichtbarer Loading-State beim Login/Register (Spinner + disabled CTA)
- Eindeutige Statusmeldungen (inkl. Verifizierungshinweis)
- Verbesserte visuelle Darstellung (kein „grauer Mini-Hinweis")
- Konsistente Message-Texte über alle Auth-Pfade

## Out of Scope
- Neue Provider-Logins (Google/Apple) in diesem Ticket

## Akzeptanzkriterien
- Nutzer erkennt jederzeit: idle/loading/error/success.
- Verifizierungsfall klar verständlich und prominent.
- Kein inkonsistentes Wording im Auth-Bereich.

## DoD
- UI/VM-States für Auth sauber abgebildet.
- Mind. ein UI-Test/Snapshot pro Hauptzustand.
- Produkt-Review: UX wirkt „fertig“, nicht provisorisch.

## Testfälle
1. Login mit langsamem Netz -> Loading-State sichtbar.
2. Register mit Email-Verify erforderlich -> klare Info + nächste Schritte.
3. Falsches Passwort -> präzise Fehlermeldung, kein technischer Jargon.

## Risiken
- Asynchrone Zustandswechsel führen zu Flackern/Fehlzustand.

## Artefakte
- Auth-UI Screenshots vorher/nachher
- Testprotokoll (neuer Mac)
