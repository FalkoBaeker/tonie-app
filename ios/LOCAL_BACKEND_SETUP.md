# Local Backend Setup (iOS MVP)

## 1) Backend lokal starten

Im Repo-Root:

```bash
cd backend
./.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8787 --reload
```

Wichtig:
- `--host 0.0.0.0` ist nötig, damit iPhone im WLAN den Server erreicht.
- Bei Simulator geht auch `127.0.0.1`, aber mit `0.0.0.0` deckst du beide Fälle ab.

## 2) Mac-IP für echtes iPhone finden

```bash
ipconfig getifaddr en0
```

Falls leer (z. B. Ethernet/anderes Interface), prüfe Interfaces:

```bash
ifconfig | grep "inet "
```

Dann die passende lokale IP nutzen (typisch `192.168.x.y`).

## 3) Base URL in der iOS-App

Die App liest `TF_API_BASE_URL` aus Info.plist/Build Settings.

Aktuelle Defaults:
- **Simulator**: `http://127.0.0.1:8787/api`
- **Echtes Gerät (iphoneos)**: `http://192.168.178.100:8787/api` (Platzhalter, auf deine Mac-IP ändern)

Für ein echtes iPhone musst du die `iphoneos` URL auf deine echte Mac-IP setzen, z. B.:

`http://192.168.178.42:8787/api`

## 4) Auth-Mode (local vs external)

Die iOS-App unterstützt zwei Modi über Build-Settings / Info.plist:

- `TF_AUTH_MODE=local`
  - nutzt Backend `/auth/register` + `/auth/login` (lokaler Dev-Auth)
- `TF_AUTH_MODE=external`
  - nutzt Supabase Auth (Email/Passwort) für Access Token
  - sendet Supabase Bearer Token an Backend (`AUTH_MODE=external`)

Zusätzliche Werte für external mode:
- `TF_SUPABASE_URL=https://<project-ref>.supabase.co` (Platzhalter `<project-ref>` durch echten Wert ersetzen)
- `TF_SUPABASE_ANON_KEY=<supabase-anon-key>` (Platzhalter ersetzen)

Wichtig:
- App nach Env-Änderungen aus Xcode neu starten (ggf. App auf Device einmal löschen), sonst läuft evtl. noch alte Config.
- In **Account -> Diagnostics** prüfen:
  - `Auth Mode: external`
  - `Base URL` zeigt Staging URL
  - `... Source` zeigt, ob Wert aus `env:` oder `plist:` kommt

Hinweis:
- Bei aktivierter Email-Verifikation zeigt die App nach Registrierung einen Hinweis zur Bestätigungsmail.

## 5) ATS / HTTP (wichtig für lokales Backend)

Da lokal oft über `http://` gearbeitet wird (ohne TLS), blockt iOS sonst Requests durch ATS.

Für das lokale MVP ist aktuell in den Build-Settings gesetzt:
- `NSAppTransportSecurity -> NSAllowsArbitraryLoads = YES`

Das ist für lokalen Dev-Betrieb okay, aber **nicht** für Production.

Später für Deploy:
- Auf HTTPS umstellen
- ATS-Ausnahmen entfernen oder minimal einschränken

## 6) Quick Verify

Backend Health im Browser/Terminal prüfen:

```bash
curl http://127.0.0.1:8787/api/health
curl http://<MAC_IP>:8787/api/health
```

Wenn beide Antworten liefern, sind Simulator + iPhone-Pfad korrekt vorbereitet.

## 7) XCTest / xcodebuild test Command

Für den minimalen iOS-Test-Slice (Task 3, APIErrorTests):

```bash
xcodebuild \
  -project ios/TonieFinder.xcodeproj \
  -scheme TonieFinder \
  -configuration Debug \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  -only-testing:TonieFinderTests/APIErrorTests \
  test
```

Komplette Scheme-Tests:

```bash
xcodebuild \
  -project ios/TonieFinder.xcodeproj \
  -scheme TonieFinder \
  -configuration Debug \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  test
```
