# Tonie Finder DB Backup / Restore (5-Min Guide)

## Purpose

Create and restore consistent SQLite backups for production-like operation.

The scripts use SQLite's built-in backup API to produce a consistent snapshot.

## Backup

```bash
cd backend
python3 scripts/db_backup.py --out backups/tonie_finder_$(date +%Y%m%d_%H%M%S).db
```

Result: backup file at the provided path.

## Restore

```bash
cd backend
python3 scripts/db_restore.py --in backups/tonie_finder_YYYYMMDD_HHMMSS.db
```

Behavior:

- restores into configured `settings.sqlite_path`
- removes stale `-wal` / `-shm` sidecars before restore

## Quick verification

```bash
cd backend
python3 -m unittest discover -s tests -p 'test_*.py'
```

Then call health endpoint:

```bash
curl -s http://127.0.0.1:8787/api/health
```

Expected: `ok: true` and `db.status: "ok"`.
