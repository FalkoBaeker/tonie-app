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

## Schnellablauf für Alltag

```bash
cd backend
./ops/launchd/install_launchd_service.sh
./scripts/backend_status.sh
./scripts/backend_smoke.sh
```
