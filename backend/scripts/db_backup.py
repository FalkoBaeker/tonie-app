from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from app.core.config import settings
from app.services.persistence import init_db

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _resolve_sqlite_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (_BACKEND_ROOT / path).resolve()
    return path


def backup_sqlite_database(*, out_path: Path, sqlite_path: Path | None = None) -> Path:
    init_db()

    source_path = sqlite_path or _resolve_sqlite_path(settings.sqlite_path)
    destination = out_path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(str(source_path), timeout=30) as source_conn:
        with sqlite3.connect(str(destination), timeout=30) as destination_conn:
            source_conn.backup(destination_conn)

    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a consistent SQLite backup for Tonie Finder.")
    parser.add_argument("--out", required=True, help="Output backup file path (e.g. backups/tonie_finder.db)")
    args = parser.parse_args()

    out_path = Path(args.out)
    written = backup_sqlite_database(out_path=out_path)
    print(f"backup written: {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
