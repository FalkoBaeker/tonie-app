from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app
from app.services import market_refresh


class ApiRefreshLockingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_sqlite_path = settings.sqlite_path

        db_path = Path(self._tmp.name) / "refresh_locking.db"
        settings.sqlite_path = str(db_path)

        self.client = TestClient(create_app())
        self.client.__enter__()

    def tearDown(self) -> None:
        if market_refresh._LOCK.locked():
            market_refresh._LOCK.release()

        self.client.__exit__(None, None, None)
        settings.sqlite_path = self._old_sqlite_path
        self._tmp.cleanup()

    def test_second_sync_refresh_returns_409_when_running(self) -> None:
        asyncio.run(market_refresh._LOCK.acquire())

        res = self.client.post(
            "/api/market/refresh",
            json={"background": False, "limit": 1, "delay_ms": 0, "max_items": 10},
        )

        self.assertEqual(res.status_code, 409, msg=res.text)
        self.assertEqual(res.json().get("detail"), "refresh already running")

    def test_background_refresh_returns_409_when_running(self) -> None:
        asyncio.run(market_refresh._LOCK.acquire())

        res = self.client.post(
            "/api/market/refresh",
            json={"background": True, "limit": 1, "delay_ms": 0, "max_items": 10},
        )

        self.assertEqual(res.status_code, 409, msg=res.text)
        self.assertEqual(res.json().get("detail"), "refresh already running")


if __name__ == "__main__":
    unittest.main()
