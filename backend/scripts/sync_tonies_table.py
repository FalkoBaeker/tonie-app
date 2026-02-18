#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.services.persistence import init_db
from app.services.tonie_resolver import get_resolver


def _db_path() -> Path:
    path = Path(settings.sqlite_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def main() -> int:
    init_db()
    resolver = get_resolver()
    catalog = resolver.catalog

    db_path = _db_path()
    now = _now_iso()

    with sqlite3.connect(db_path, timeout=30) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tonies (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                series TEXT,
                aliases_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tonies_title ON tonies(title)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tonies_series ON tonies(series)")

        existing_ids = {
            str(row[0])
            for row in conn.execute("SELECT id FROM tonies")
        }

        inserted = 0
        updated = 0

        for item in catalog:
            tonie_id = str(item.get("id") or "").strip()
            if not tonie_id:
                continue

            title = str(item.get("title") or "").strip() or tonie_id
            series = str(item.get("series") or "").strip() or None
            aliases = item.get("aliases") or []
            aliases_json = json.dumps([str(a) for a in aliases if str(a).strip()], ensure_ascii=False)

            if tonie_id in existing_ids:
                updated += 1
                conn.execute(
                    """
                    UPDATE tonies
                    SET title = ?, series = ?, aliases_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (title, series, aliases_json, now, tonie_id),
                )
            else:
                inserted += 1
                conn.execute(
                    """
                    INSERT INTO tonies(id, title, series, aliases_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (tonie_id, title, series, aliases_json, now, now),
                )

        total = int(conn.execute("SELECT COUNT(*) FROM tonies").fetchone()[0])

    print(f"db_path={db_path}")
    print(f"catalog_items={len(catalog)}")
    print(f"inserted={inserted}")
    print(f"updated={updated}")
    print(f"tonies_total={total}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
