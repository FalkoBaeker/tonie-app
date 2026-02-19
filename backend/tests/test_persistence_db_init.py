from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import settings
from app.services import persistence


class _WalFailConnection:
    def __init__(self, conn: sqlite3.Connection) -> None:
        object.__setattr__(self, "_conn", conn)

    def __getattr__(self, name: str):
        return getattr(self._conn, name)

    def __setattr__(self, name: str, value):
        setattr(self._conn, name, value)

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        return self._conn.__exit__(exc_type, exc, tb)

    def execute(self, sql: str, *args, **kwargs):
        if sql.strip().upper() == "PRAGMA JOURNAL_MODE = WAL":
            raise sqlite3.OperationalError("WAL unavailable")
        return self._conn.execute(sql, *args, **kwargs)


class PersistenceDbInitTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_sqlite_path = settings.sqlite_path

    def tearDown(self) -> None:
        settings.sqlite_path = self._old_sqlite_path
        self._tmp.cleanup()

    def test_init_db_creates_database_file_in_nested_path(self) -> None:
        db_path = Path(self._tmp.name) / "nested" / "state" / "watchlist.db"
        settings.sqlite_path = str(db_path)

        persistence.init_db()

        self.assertTrue(db_path.exists())
        self.assertGreater(db_path.stat().st_size, 0)

    def test_init_db_falls_back_when_wal_not_available(self) -> None:
        db_path = Path(self._tmp.name) / "wal-fallback.db"
        settings.sqlite_path = str(db_path)

        real_connect = sqlite3.connect

        def _connect(*args, **kwargs):
            return _WalFailConnection(real_connect(*args, **kwargs))

        with patch("app.services.persistence.sqlite3.connect", side_effect=_connect):
            persistence.init_db()

        self.assertTrue(db_path.exists())


if __name__ == "__main__":
    unittest.main()
