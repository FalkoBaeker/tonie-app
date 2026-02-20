# S7-07 — Fotoerkennung-Risiko-Reduktion

## Typ
Should

## Ziel
Fotoerkennung von „unsicherem Raten“ zu kontrolliert assistivem Matching entwickeln.

## Scope
- Benchmark-Set für echte Tonie-Fälle aufbauen
- Messgrößen definieren (Top-1/Top-3, Confusion Cases)
- Katalog-/Retrieval-basierte Kandidatenfindung stärken
- Low-confidence Fallback mit Nutzerbestätigung erzwingen

## Out of Scope
- Vollautomatisches Auto-Matching ohne User-Confirm

## Akzeptanzkriterien
- Qualität ist messbar (nicht nur subjektiv).
- Niedrige Confidence führt nie zu blindem finalem Match.
- UX erklärt Unsicherheit klar.

## DoD
- Benchmark-Dokument + erstes Ergebnisprotokoll vorhanden.
- Entscheidungsregel für Confidence implementiert/dokumentiert.
- Product-Decision: assistiv in v1, keine Auto-Commit-Erkennung.

## Testfälle
1. Klare Referenzbilder -> korrekte Top-3 Kandidaten.
2. Schwieriger Case (ähnliche Figuren) -> sichere Bestätigungsführung.
3. Irrelevantes Bild -> sauberer `not_found`/`needs_confirmation`-Pfad.

## Risiken
- Schlechte Referenzdaten dominieren Ergebnisqualität.

## Artefakte
- `docs/quality/photo-recognition-benchmark.md`
- Fehlerfall-Katalog (Top-Confusions)
