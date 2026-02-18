# Tonie Finder (iOS, Deutschland) — Product Spec v1

## Ziel
Für einen eingegebenen oder fotografierten Tonie drei verwertbare Preise liefern:
1. Sofortverkaufspreis
2. Fairer Marktpreis
3. Geduldspreis

## Plattform
- iOS first
- Markt: Deutschland
- Sprache: Deutsch

## Branding / Design
- App-Name: **Tonie Finder**
- Design: clean, minimalistisch
- Primärfarbe: Tonie-Rot
- Akzent: Silver Shadows / Apple-artiger Luxury Touch

## Kernfunktionen
1. **Tonie-Suche per Text**
   - Tippfehler-tolerant
   - automatische Normalisierung (z. B. ähnliche Titel)
   - bei Mehrdeutigkeit: Auswahl-Liste mit Bildern
   - wenn unklar: klare Meldung „Nicht eindeutig gefunden“ (kein falscher Preis)

2. **Zustand-Auswahl (Dropdown)**
   - Neu versiegelt (OVP)
   - Neu offen
   - Sehr gut
   - Gut
   - Stark bespielt
   - Defekt

3. **Fotoerkennung (ausgepackte Figur, ohne Barcode/OVP)**
   - Foto -> Tonie-Kandidat + Alternativen
   - bei Unsicherheit: Nutzer muss wählen

4. **Preis-Ausgabe (kein Intervall)**
   - Sofortverkaufspreis (Q25)
   - Fairer Marktpreis (Q50)
   - Geduldspreis (Q75)
   - ohne Versandkosten
   - Bundle-Angebote werden entfernt

5. **Watchlist**
   - Tonies merken
   - Preisänderungen sehen

6. **Login + Backend**
   - Benutzerkonto
   - geräteübergreifende Sync

## Datenquellen (priorisiert)
1. eBay (verkaufte/abgeschlossene Verkäufe priorisiert)
2. Kleinanzeigen (aktive Inserate, gewichtet)
3. Vinted (aktive Inserate, gewichtet)
4. Spezialforen/FB-Gruppen: optional später nur wenn technisch/rechtlich sauber erfassbar

## Preislogik
- Primärquelle: abgeschlossene Verkäufe (realistischster Marktanker)
- Sekundär: aktive Inserate mit Abschlagfaktor
- Zeitfenster dynamisch:
  - Standard: 90 Tage
  - bei hoher Aktivität: 30–60 Tage
  - bei seltenen Raritäten: bis 180 Tage als Fallback
- Ausreißerfilter:
  - Duplikate raus
  - Bundle raus
  - „defekt/fake/lot“ raus (Regelset)

## Nicht-Ziele in v1
- Automatisches Inserieren auf Marktplätzen
- DACH/International
- Desktop/Web-Client

## Delivery Constraints
- Aktuell noch kein Apple Developer Account vorhanden
- Entwicklung startet simulator-first, Account wird für TestFlight/App Store später benötigt

## Erfolgskriterien (MVP)
- >=85% korrekte Tonie-Zuordnung bei Texteingabe
- >=75% Top-3 Treffer bei Fotoerkennung
- Preisvorschläge bei häufigen Tonies in <3 Sekunden
- Kein Preis, wenn Identität nicht sicher (Fail-safe)
