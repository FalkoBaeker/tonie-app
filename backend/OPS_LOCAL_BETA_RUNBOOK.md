# Tonie Finder – Local WLAN Beta Ops Runbook

Ziel: Backend lokal stabil betreiben (Start/Stop/Status/Recovery) ohne Feature-Scope.

## Voraussetzungen

```bash
cd backend
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env
mkdir -p backups logs
```

## Auth mode quick note (Local vs Production)

- Local dev/beta currently uses `AUTH_MODE=local`.
- Production target is `AUTH_MODE=external` with provider JWT validation via JWKS.
- Umschalten:
  - setze in `.env`: `AUTH_MODE=external`
  - setze `AUTH_JWKS_URL` (+ optional `AUTH_ISSUER`, `AUTH_AUDIENCE`)
  - optional strict: `AUTH_REQUIRE_VERIFIED_EMAIL=true`
- Rollback: `AUTH_MODE=local` und Backend neu starten.

## Start / Stop / Logs

### Start (Foreground, manuell)
```bash
cd backend
./.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8787
```

### Stop (Foreground)
- Im Terminal mit laufendem `uvicorn`: `Ctrl+C`

### Logs (bei launchd-Betrieb)
```bash
cd backend
tail -f logs/backend.stdout.log logs/backend.stderr.log
```

## Health / Monitoring

### Einmaliger Health-Status
```bash
cd backend
./scripts/backend_status.sh
```

Beispiel-Output:
- `UP http=200 ok=true db=ok market_refresh=idle ...`
- `DOWN http=... reason=...`

### Optional: laufende Beobachtung (alle 10s)
```bash
cd backend
while true; do ./scripts/backend_status.sh; sleep 10; done
```

### API-Smoke (Happy Path)
```bash
cd backend
./scripts/backend_smoke.sh
```

Prüft:
1. `/api/health`
2. `/api/auth/register`
3. `/api/auth/me`
4. `/api/tonies/resolve`
5. `/api/pricing/{tonie_id}`

### Preflight vor Feldtest
```bash
cd backend
./scripts/preflight_beta.sh
```

Exit Codes:
- `0` = alle Checks ok
- `!=0` = mindestens ein Check fehlgeschlagen

## Backup / Restore

### Backup erstellen
```bash
cd backend
./.venv/bin/python scripts/db_backup.py --out backups/tonie_finder_$(date +%Y%m%d_%H%M%S).db
```

### Restore einspielen
```bash
cd backend
./.venv/bin/python scripts/db_restore.py --in backups/tonie_finder_YYYYMMDD_HHMMSS.db
```

Hinweis: Restore überschreibt den aktuellen DB-Stand (inkl. potentiell neuerer Daten).

## Auto-Start / Restart (launchd, macOS)

### Installieren + aktivieren
```bash
cd backend
./ops/launchd/install_launchd_service.sh
```

### Status prüfen
```bash
launchctl print gui/$(id -u)/com.falko.toniefinder.backend | head -n 20
```

### Neustarten
```bash
launchctl kickstart -k gui/$(id -u)/com.falko.toniefinder.backend
```

### Deaktivieren / entfernen
```bash
cd backend
./ops/launchd/uninstall_launchd_service.sh
```

## Wenn etwas kaputt ist (Failure Playbook)

### 1) Port 8787 belegt / mehrere uvicorn-Prozesse
```bash
lsof -nP -iTCP:8787 -sTCP:LISTEN
pkill -f "uvicorn app.main:app" || true
./scripts/backend_status.sh
```

### 2) Health DOWN
```bash
./scripts/backend_status.sh
./ops/launchd/install_launchd_service.sh
./scripts/backend_status.sh
```

### 3) launchd service nicht geladen / failed
```bash
launchctl print gui/$(id -u)/com.falko.toniefinder.backend | head -n 30
./ops/launchd/uninstall_launchd_service.sh
./ops/launchd/install_launchd_service.sh
```

### 4) DB-Stand zurücksetzen (Restore)
```bash
ls -lt backups | head
./.venv/bin/python scripts/db_restore.py --in backups/<backup-file>.db
./scripts/backend_status.sh
```

## Schnellablauf für Alltag

```bash
cd backend
./ops/launchd/install_launchd_service.sh
./scripts/preflight_beta.sh
```
