from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from app.core.config import settings

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _resolve_sqlite_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (_BACKEND_ROOT / path).resolve()
    return path


def restore_sqlite_database(*, backup_path: Path, sqlite_path: Path | None = None) -> Path:
    source_path = backup_path.expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"backup file not found: {source_path}")

    destination = sqlite_path or _resolve_sqlite_path(settings.sqlite_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    wal_path = destination.with_name(destination.name + "-wal")
    shm_path = destination.with_name(destination.name + "-shm")
    for sidecar in (wal_path, shm_path):
        if sidecar.exists():
            sidecar.unlink()

    with sqlite3.connect(str(source_path), timeout=30) as source_conn:
        with sqlite3.connect(str(destination), timeout=30) as destination_conn:
            source_conn.backup(destination_conn)

    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore Tonie Finder SQLite DB from backup.")
    parser.add_argument("--in", dest="in_path", required=True, help="Input backup file path")
    args = parser.parse_args()

    restored = restore_sqlite_database(backup_path=Path(args.in_path))
    print(f"database restored: {restored}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
