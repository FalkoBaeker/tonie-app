from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api import routes
from app.core.config import settings
from app.main import create_app
from app.services.pricing_engine import EnginePriceResult
from app.services.tonie_resolver import get_resolver


class ApiWatchlistAlertsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_sqlite_path = settings.sqlite_path
        self._old_compute_prices = routes.compute_prices_for_tonie

        db_path = Path(self._tmp.name) / "watchlist_alerts.db"
        settings.sqlite_path = str(db_path)

        self._prices: list[float] = []

        async def _fake_compute_prices_for_tonie(*, tonie_id: str, condition: str) -> EnginePriceResult:
            _ = (tonie_id, condition)
            fair = self._prices.pop(0) if self._prices else 100.0
            return EnginePriceResult(
                instant=round(fair * 0.9, 2),
                fair=fair,
                patience=round(fair * 1.1, 2),
                sample_size=12,
                source="ebay_sold_live_q25_q50_q75",
                effective_sample_size=12.0,
            )

        routes.compute_prices_for_tonie = _fake_compute_prices_for_tonie

        self.client = TestClient(create_app())
        self.client.__enter__()

        register = self.client.post(
            "/api/auth/register",
            json={"email": "alerts@example.com", "password": "secret123"},
        )
        self.assertEqual(register.status_code, 200, msg=register.text)
        self.token = register.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        routes.compute_prices_for_tonie = self._old_compute_prices
        settings.sqlite_path = self._old_sqlite_path
        self._tmp.cleanup()

    def test_watchlist_alerts_price_below_target_and_drop(self) -> None:
        resolver = get_resolver()
        known_tonie_id = str(resolver.catalog[0]["id"])

        # initial add uses fair=100.0
        self._prices = [100.0]
        add = self.client.post(
            "/api/watchlist",
            headers=self.headers,
            json={
                "tonie_id": known_tonie_id,
                "condition": "good",
                "target_price_eur": 90.0,
            },
        )
        self.assertEqual(add.status_code, 200, msg=add.text)

        # refresh updates fair to 80.0 => below target + 20% drop
        self._prices = [80.0]
        refreshed = self.client.get("/api/watchlist?refresh=true", headers=self.headers)
        self.assertEqual(refreshed.status_code, 200, msg=refreshed.text)

        alerts = self.client.get("/api/watchlist/alerts", headers=self.headers)
        self.assertEqual(alerts.status_code, 200, msg=alerts.text)
        rows = alerts.json()
        self.assertEqual(len(rows), 2)

        alert_types = {row["alert_type"] for row in rows}
        self.assertEqual(alert_types, {"price_below_target", "price_drop_15pct"})

        below_target = next(row for row in rows if row["alert_type"] == "price_below_target")
        self.assertEqual(float(below_target["target_price_eur"]), 90.0)
        self.assertEqual(float(below_target["current_price_eur"]), 80.0)

        unread = self.client.get("/api/watchlist/alerts?unread_only=true", headers=self.headers)
        self.assertEqual(unread.status_code, 200, msg=unread.text)
        self.assertEqual(len(unread.json()), 2)

    def test_watchlist_alerts_empty_when_no_rule_matches(self) -> None:
        resolver = get_resolver()
        known_tonie_id = str(resolver.catalog[0]["id"])

        self._prices = [100.0]
        add = self.client.post(
            "/api/watchlist",
            headers=self.headers,
            json={"tonie_id": known_tonie_id, "condition": "good"},
        )
        self.assertEqual(add.status_code, 200, msg=add.text)

        # 5% drop only, no target configured => no alerts
        self._prices = [95.0]
        refreshed = self.client.get("/api/watchlist?refresh=true", headers=self.headers)
        self.assertEqual(refreshed.status_code, 200, msg=refreshed.text)

        alerts = self.client.get("/api/watchlist/alerts", headers=self.headers)
        self.assertEqual(alerts.status_code, 200, msg=alerts.text)
        self.assertEqual(alerts.json(), [])


if __name__ == "__main__":
    unittest.main()
