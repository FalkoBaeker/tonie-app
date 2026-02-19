from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import routes
from app.core.config import settings
from app.main import create_app
from app.services.persistence import init_db
from scripts.db_backup import backup_sqlite_database


class ApiHealthAndBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_sqlite_path = settings.sqlite_path
        settings.sqlite_path = str(Path(self._tmp.name) / "health_backup.db")

        self.client = TestClient(create_app())
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        settings.sqlite_path = self._old_sqlite_path
        self._tmp.cleanup()

    def test_health_includes_db_readiness_fields(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200, msg=response.text)

        payload = response.json()
        self.assertIn("ok", payload)
        self.assertIn("status", payload)
        self.assertIn("reason", payload)
        self.assertIn("db", payload)
        self.assertIn("market_refresh", payload)
        self.assertIn("ok", payload["db"])
        self.assertIn("status", payload["db"])
        self.assertIn("sqlite_path", payload["db"])

    def test_health_returns_degraded_when_db_check_fails(self) -> None:
        degraded = {
            "ok": False,
            "status": "degraded",
            "reason": "sqlite_operational_error: unable to open database file",
            "sqlite_path": "/tmp/missing.db",
        }

        with patch.object(routes, "get_db_readiness", return_value=degraded):
            response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200, msg=response.text)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["reason"], degraded["reason"])
        self.assertEqual(payload["db"]["status"], "degraded")

    def test_backup_script_creates_backup_file(self) -> None:
        init_db()

        out_path = Path(self._tmp.name) / "backups" / "snapshot.db"
        written = backup_sqlite_database(
            out_path=out_path,
            sqlite_path=Path(settings.sqlite_path),
        )

        self.assertEqual(written, out_path.resolve())
        self.assertTrue(written.exists())
        self.assertGreater(written.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
