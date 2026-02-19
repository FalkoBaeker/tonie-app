# TestFlight RC Packaging – TonieFinder

Ziel: Ein reproduzierbarer, upload-fähiger RC-Archive-Flow für den **NEUEN Mac**.

## 1) Voraussetzungen

- Repo-Stand: `main` (aktueller RC-Commit)
- Xcode: aktuelles stabiles Release
- Scheme: `TonieFinder`
- Bundle ID: `com.falko.toniefinder`
- Signing/Team: in Xcode für Release korrekt gesetzt (Apple Team/Certificates/Profiles)

## 2) RC Build-Identität

- Marketing Version: `0.1.2`
- Build Number: `3`
- Release Notes: `ios/RELEASE_NOTES.md`

## 3) Archive bauen (Xcode UI)

1. `ios/TonieFinder.xcodeproj` in Xcode öffnen.
2. Scheme oben auf `TonieFinder` stellen.
3. Target Device auf **Any iOS Device (arm64)** setzen.
4. `Product` → `Archive`.
5. Nach erfolgreichem Build öffnet sich Organizer mit neuem Archive.

## 4) Archive bauen (CLI-Alternative)

```bash
cd ios
xcodebuild archive \
  -scheme TonieFinder \
  -configuration Release \
  -destination 'generic/platform=iOS' \
  -archivePath build/TonieFinder.xcarchive
```

(Optionaler Export später via Organizer oder `xcodebuild -exportArchive` mit ExportOptions.plist.)

## 5) Pre-Upload Checkliste

Vor Upload einmal durchgehen:

- [ ] `git pull origin main` ist aktuell
- [ ] `ios/RELEASE_NOTES.md` passt zu Version/Build
- [ ] Smoke-Checks durchgeführt (siehe `ios/SMOKE_TEST_CHECKLIST.md`)
- [ ] Auth, Pricing/Resolve, Watchlist, Alerts, Diagnostics geprüft
- [ ] Diagnostics sichtbar inkl. Base URL/Session/Debug + Version/Build
- [ ] Release Archive ohne Signing-Fehler erzeugt

## 6) Known Issues / Beta-Testfokus

Known issues:
- Backend muss erreichbar sein (base URL)
- Bei instabilen Netzen können temporäre API-Fehler auftreten

Beta-Testfokus:
1. Login/Session-Restore
2. Resolve/Pricing (inkl. Retry)
3. Watchlist CRUD + Refresh
4. Alerts + unread toggle
5. Diagnostics inkl. Debug-Log-Verhalten (`TF_DEBUG_LOG=1`)
