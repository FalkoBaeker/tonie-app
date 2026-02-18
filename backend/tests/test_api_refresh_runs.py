from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app
from app.services.persistence import create_refresh_run


class ApiRefreshRunsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_sqlite_path = settings.sqlite_path

        db_path = Path(self._tmp.name) / "refresh_runs.db"
        settings.sqlite_path = str(db_path)

        now = datetime.now(UTC)
        for idx in range(3):
            started = (now - timedelta(minutes=idx + 1)).isoformat()
            finished = (now - timedelta(minutes=idx)).isoformat()
            create_refresh_run(
                {
                    "run_id": f"run_{idx}",
                    "status": "completed",
                    "started_at": started,
                    "finished_at": finished,
                    "total": 10,
                    "processed": 10,
                    "successful": 10,
                    "failed": 0,
                    "saved_rows": 20 + idx,
                    "pruned_rows": 3,
                    "limit": 10,
                    "delay_ms": 0,
                    "max_items": 80,
                    "failures": [],
                }
            )

        self.client = TestClient(create_app())
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        settings.sqlite_path = self._old_sqlite_path
        self._tmp.cleanup()

    def test_refresh_runs_endpoint_returns_items_sorted_and_typed(self) -> None:
        res = self.client.get("/api/market/refresh-runs?limit=2")
        self.assertEqual(res.status_code, 200, msg=res.text)

        body = res.json()
        self.assertIn("items", body)
        items = body["items"]
        self.assertEqual(len(items), 2)

        # newest started_at first (run_0 then run_1)
        self.assertEqual(items[0]["run_id"], "run_0")
        self.assertEqual(items[1]["run_id"], "run_1")

        first = items[0]
        required = {
            "run_id",
            "status",
            "started_at",
            "finished_at",
            "total",
            "processed",
            "successful",
            "failed",
            "saved_rows",
            "pruned_rows",
            "limit",
            "delay_ms",
            "max_items",
            "failures",
        }
        self.assertTrue(required.issubset(first.keys()))
        self.assertIsInstance(first["total"], int)
        self.assertIsInstance(first["processed"], int)
        self.assertIsInstance(first["saved_rows"], int)
        self.assertIsInstance(first["failures"], list)


if __name__ == "__main__":
    unittest.main()
