# Photo Recognition Benchmark & Risk Plan (S7-07)

Stand: 2026-02-20
Status: v1 Benchmark-Design + Produktentscheidung

## 1) Ziel
Fotoerkennung in Tonie Finder soll **assistiv** sein (Kandidaten vorschlagen), nicht blind automatisch entscheiden.

## 2) Aktueller technischer Stand
Backend erkennt aktuell über lokalen Referenzindex:
- dHash + mittlere RGB-Farbe
- kombinierter Score: `0.86 * hash_similarity + 0.14 * color_similarity`
- Statuspfade:
  - `resolved`
  - `needs_confirmation`
  - `not_found`
  - `not_configured`

Schwellwerte aus Config:
- `recognition_min_score` (default 0.72)
- `recognition_resolved_score` (default 0.90)
- `recognition_resolved_gap` (default 0.06)

## 3) Messdesign

### 3.1 Datensatz
Für den ersten belastbaren Benchmark:
- **30 Tonies** (repräsentativ: beliebt + ähnlich aussehende Figuren)
- pro Tonie:
  - 8 Referenzbilder (Index-Set)
  - 6 Testbilder (Holdout, nicht im Index)
- zusätzlich:
  - 60 Negativbilder (kein Tonie / falscher Tonie-Kontext)

Gesamt erste Benchmark-Runde:
- Positiv: 180 Holdout-Bilder
- Negativ: 60 Bilder
- Total: 240 Bilder

### 3.2 Metriken
- **Top-1 Accuracy**: korrekter Tonie an Position 1
- **Top-3 Recall**: korrekter Tonie in Top-3 enthalten
- **False Positive Rate (FPR)** auf Negativbildern
- **Auto-Resolve Precision**: Präzision nur für Fälle mit Status `resolved`
- **Needs-Confirmation Rate**: Anteil, der manuelle Bestätigung braucht

### 3.3 Fehlerklassen (Pflicht-Labeling)
Jeder Fehlfall wird einer Klasse zugeordnet:
1. Ähnliche Figur derselben Serie
2. Starke Perspektiv-/Lichtabweichung
3. Teilverdeckung/unscharf
4. Hintergrund dominiert Objekt
5. Fehlende/zu schwache Referenzbilder
6. Nicht-Tonie wurde fälschlich gematcht

## 4) Confidence- und Fallback-Regeln (Produkt)

### 4.1 Harte Produktregel v1
- **Kein blindes Auto-Match für Endnutzeraktionen.**
- Selbst bei `resolved` wird der Treffer in der UI klar angezeigt und bleibt nachvollziehbar.

### 4.2 Status-Verhalten
- `resolved`: Top-1 anzeigen, Nutzer kann direkt fortfahren
- `needs_confirmation`: immer Top-3 Auswahl zeigen, Nutzer muss bestätigen
- `not_found`: klare Rückfalloption auf Textsuche
- `not_configured`: Feature-Hinweis statt irreführender Fehlermeldung

### 4.3 Guardrails
- Bei sehr ähnlichen Scores (kleine Top1-Top2 Lücke) niemals Auto-Commit
- Bei Negativmustern (kein Tonie-Kontext) bevorzugt `not_found`

## 5) Zielwerte für v1-Freigabe
Für den ersten produktiven Einsatz (assistiv):
- Top-1 Accuracy >= 75%
- Top-3 Recall >= 92%
- FPR auf Negativbildern <= 5%
- Auto-Resolve Precision >= 95%

Wenn ein Zielwert verfehlt wird:
- `resolved`-Schwellen konservativer setzen
- mehr Fälle über `needs_confirmation` routen
- Referenzkatalog gezielt ausbauen

## 6) Operativer Ablauf (Benchmark Runbook)
1. Referenzbilder strukturieren unter `backend/app/data/tonie_refs/<tonie_id>/...`
2. Index bauen: `python scripts/build_photo_reference_index.py`
3. Testset gegen `/api/tonies/recognize` laufen lassen
4. Ergebnisse in CSV/JSON protokollieren (expected vs predicted + score + status)
5. Fehlerfälle nach Klassen labeln
6. Schwellenwerte iterativ kalibrieren

## 7) Risiken & Gegenmaßnahmen
- Risiko: Zu wenige/inkonsistente Referenzbilder -> schlechte Generalisierung
  - Maßnahme: Mindeststandard pro Tonie (Licht/Front/seitlich)
- Risiko: Visuell ähnliche Figuren verwechselt
  - Maßnahme: konservative `resolved`-Regeln + Confirmation-Flow
- Risiko: Nutzer erwartet Vollautomatik
  - Maßnahme: UI-Text klar: „Vorschlag, bitte bestätigen"

## 8) Produktentscheidung für v1
**Entscheidung: assistiver Modus, kein blindes Auto-Match.**

Begründung:
- Deutlich geringeres Fehlzuordnungsrisiko
- Bessere UX-Kontrolle bei ähnlichen Figuren
- Stabiler Startpunkt bis Benchmark-Zielwerte robust erreicht sind
