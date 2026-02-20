# S7-04 — Alerts produktisieren

## Typ
Must

## Ziel
Alerts-Tab von „vorhanden“ zu „nutzbar und wertstiftend“ entwickeln.

## Scope
- Trigger klar definieren:
  1) Preis unter Zielpreis
  2) Preisdrop über Schwellwert
- Alert-Text mit Begründung („warum ausgelöst")
- Filter „neu/alle" + sauberer Empty-State
- Klarer Zeitbezug (wann ausgelöst)

## Out of Scope
- Push-Notification-Infrastruktur (optional S8)

## Akzeptanzkriterien
- Nutzer versteht jeden Alert ohne technische Details.
- Mind. 2 Alert-Typen sind in E2E reproduzierbar.
- Empty-State erklärt, wie Alerts entstehen.

## DoD
- Alert-UX inkl. Filter vollständig.
- API/UI-Verhalten für unread_only konsistent.
- Testfälle für beide Triggerarten dokumentiert.

## Testfälle
1. Zielpreis setzen + Preis darunter -> Alert sichtbar.
2. Prozentualer Drop über Schwellwert -> Alert sichtbar.
3. Keine passenden Bedingungen -> Empty-State statt Verwirrung.

## Risiken
- Zu viele/zu häufige Alerts (Spam-Gefahr).

## Artefakte
- Alert-Decision-Logik dokumentiert
- Screenshots der Alert-Zustände
