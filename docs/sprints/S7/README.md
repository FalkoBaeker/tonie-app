# S7 — Release-Readiness Sprint

## Ziel
S7 macht Tonie Finder release-fähig: Legal/GDPR-Basis, Release-Hygiene, UX-Polish, nutzbare Alerts, robuste Preis-Freshness und RC-Checkliste.

## Tickets
- [S7-01](./S7-01-legal-gdpr-basis.md) — Legal & GDPR Basis
- [S7-02](./S7-02-release-hygiene-debug-off.md) — Release-Hygiene / Debug-Off
- [S7-03](./S7-03-auth-ux-polish.md) — Auth UX Polish
- [S7-04](./S7-04-alerts-produktisieren.md) — Alerts produktisieren
- [S7-05](./S7-05-pricing-refresh-freshness.md) — Preisrefresh & Freshness
- [S7-06](./S7-06-ebay-api-spike.md) — eBay API Spike + Integrationsplan
- [S7-07](./S7-07-photo-recognition-risk-reduction.md) — Fotoerkennung-Risiko-Reduktion
- [S7-08](./S7-08-rc-checklist-testflight-prep.md) — RC-Checklist + TestFlight Prep

## Reihenfolge (kritischer Pfad)
1. S7-01
2. S7-02
3. S7-03
4. S7-04
5. S7-05
6. S7-08
7. Parallel/anschließend: S7-06, S7-07

## Globales DoD (Sprint)
- Keine offenen Release-Blocker in S7-01/02/08.
- Keine sichtbaren Debug-Elemente in Release-Build.
- Auth-Flow mit klaren Loading/Error/Success-Zuständen.
- Alerts-Tab hat klaren Nutzen (mind. 2 Triggerarten transparent).
- Preis-Freshness in UI sichtbar und technisch nachvollziehbar.
