from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import routes
from app.core.config import settings
from app.main import create_app


class ExternalAuthModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_sqlite_path = settings.sqlite_path
        self._old_auth_mode = settings.auth_mode
        self._old_require_verified = settings.auth_require_verified_email

        settings.sqlite_path = str(Path(self._tmp.name) / "external_auth.db")
        settings.auth_mode = "external"
        settings.auth_require_verified_email = True

        self.client = TestClient(create_app())
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        settings.sqlite_path = self._old_sqlite_path
        settings.auth_mode = self._old_auth_mode
        settings.auth_require_verified_email = self._old_require_verified
        self._tmp.cleanup()

    def test_me_accepts_valid_external_token_and_provisions_local_user(self) -> None:
        with patch.object(
            routes,
            "verify_external_jwt",
            return_value={
                "sub": "user-123",
                "email": "external@example.com",
                "email_verified": True,
                "exp": 9999999999,
                "iat": 1700000000,
            },
        ):
            response = self.client.get(
                "/api/auth/me",
                headers={"Authorization": "Bearer external-valid-token"},
            )

        self.assertEqual(response.status_code, 200, msg=response.text)
        body = response.json()
        self.assertEqual(body["email"], "external@example.com")
        self.assertIsInstance(body["id"], int)

    def test_me_rejects_unverified_external_email(self) -> None:
        with patch.object(
            routes,
            "verify_external_jwt",
            return_value={
                "sub": "user-999",
                "email": "external@example.com",
                "email_verified": False,
                "exp": 9999999999,
                "iat": 1700000000,
            },
        ):
            response = self.client.get(
                "/api/auth/me",
                headers={"Authorization": "Bearer external-invalid-token"},
            )

        self.assertEqual(response.status_code, 401, msg=response.text)
        self.assertIn("email not verified", response.text)

    def test_register_is_disabled_in_external_mode(self) -> None:
        response = self.client.post(
            "/api/auth/register",
            json={"email": "any@example.com", "password": "secret123"},
        )
        self.assertEqual(response.status_code, 400, msg=response.text)
        self.assertIn("local auth disabled", response.text)


if __name__ == "__main__":
    unittest.main()
