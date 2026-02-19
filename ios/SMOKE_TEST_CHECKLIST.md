# iOS MVP Smoke Test Checklist

1. App startet ohne Crash und zeigt Login oder Main Tabs.
2. Login mit gültigen Daten funktioniert, Session bleibt nach Relaunch erhalten.
3. Pricing: Resolve-Suche liefert Trefferliste und Auswahl lädt Preise.
4. Pricing-Fehler zeigt verständliche Fehlermeldung + Retry-Button.
5. Watchlist: Add-Sheet validiert `tonieId` + `title` und fügt Eintrag hinzu.
6. Watchlist: Delete entfernt Eintrag zuverlässig.
7. Watchlist: Pull-to-refresh / „Preise aktualisieren“ funktioniert ohne Endlosschleife.
8. Alerts: Liste lädt via `/api/watchlist/alerts`.
9. Alerts: Toggle „Nur ungelesene“ wechselt stabil zwischen gefiltert/unfiltered.
10. Alerts-Fehler zeigt verständliche Meldung + Retry-Button.
11. Account > Diagnostics zeigt Base URL, Session-Status und Debug-Log-Status.
12. Optional Debug: mit `TF_DEBUG_LOG=1` erscheinen API Logs (Methode/Pfad/Status, ohne Token).
13. Device/WLAN-IP Check: In **Konto → Diagnostics** prüfen, ob `Base URL` die aktuelle Backend-IP nutzt.
14. Bei WLAN-IP-Wechsel: `deviceDefault` (oder `TF_API_BASE_URL`) auf aktuelle LAN-IP setzen und App neu starten.
