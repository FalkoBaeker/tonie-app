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


class ApiMvpE2EFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_sqlite_path = settings.sqlite_path
        self._old_compute_prices = routes.compute_prices_for_tonie

        settings.sqlite_path = str(Path(self._tmp.name) / "mvp_e2e.db")

        async def _fake_compute_prices_for_tonie(*, tonie_id: str, condition: str) -> EnginePriceResult:
            _ = (tonie_id, condition)
            return EnginePriceResult(
                instant=9.99,
                fair=12.49,
                patience=14.99,
                sample_size=15,
                source="test_fixture",
                effective_sample_size=15.0,
            )

        routes.compute_prices_for_tonie = _fake_compute_prices_for_tonie

        self.client = TestClient(create_app())
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        routes.compute_prices_for_tonie = self._old_compute_prices
        settings.sqlite_path = self._old_sqlite_path
        self._tmp.cleanup()

    def test_register_login_me_resolve_pricing_watchlist_add_list_delete(self) -> None:
        # register
        register = self.client.post(
            "/api/auth/register",
            json={"email": "e2e@example.com", "password": "secret123"},
        )
        self.assertEqual(register.status_code, 200, msg=register.text)
        register_payload = register.json()
        token = register_payload["token"]
        self.assertTrue(token)

        # login
        login = self.client.post(
            "/api/auth/login",
            json={"email": "e2e@example.com", "password": "secret123"},
        )
        self.assertEqual(login.status_code, 200, msg=login.text)
        login_token = login.json()["token"]
        self.assertTrue(login_token)

        headers = {"Authorization": f"Bearer {login_token}"}

        # me
        me = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(me.status_code, 200, msg=me.text)
        self.assertEqual(me.json()["email"], "e2e@example.com")

        # resolve using known catalog id for deterministic match
        known_tonie_id = str(get_resolver().catalog[0]["id"])
        resolve = self.client.post("/api/tonies/resolve", json={"query": known_tonie_id})
        self.assertEqual(resolve.status_code, 200, msg=resolve.text)
        candidates = resolve.json().get("candidates", [])
        self.assertGreater(len(candidates), 0)
        tonie_id = candidates[0]["tonie_id"]

        # pricing
        pricing = self.client.get(f"/api/pricing/{tonie_id}?condition=good")
        self.assertEqual(pricing.status_code, 200, msg=pricing.text)
        pricing_payload = pricing.json()
        self.assertEqual(pricing_payload["fairer_marktpreis"], 12.49)

        # watchlist add
        watch_add = self.client.post(
            "/api/watchlist",
            headers=headers,
            json={"tonie_id": tonie_id, "condition": "good", "target_price_eur": 11.0},
        )
        self.assertEqual(watch_add.status_code, 200, msg=watch_add.text)
        item_id = watch_add.json()["id"]

        # watchlist list
        watch_list = self.client.get("/api/watchlist", headers=headers)
        self.assertEqual(watch_list.status_code, 200, msg=watch_list.text)
        items = watch_list.json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["tonie_id"], tonie_id)

        # watchlist delete
        watch_delete = self.client.delete(f"/api/watchlist/{item_id}", headers=headers)
        self.assertEqual(watch_delete.status_code, 200, msg=watch_delete.text)

        watch_list_after = self.client.get("/api/watchlist", headers=headers)
        self.assertEqual(watch_list_after.status_code, 200, msg=watch_list_after.text)
        self.assertEqual(watch_list_after.json(), [])


if __name__ == "__main__":
    unittest.main()
