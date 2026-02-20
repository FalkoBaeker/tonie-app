from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass
from time import time

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class EbayConfigError(RuntimeError):
    """Raised when required eBay API configuration is missing."""


class EbayAPIError(RuntimeError):
    """Raised when eBay API calls fail after retries."""


@dataclass
class EbayAccessToken:
    access_token: str
    expires_at_epoch: float

    @property
    def is_valid(self) -> bool:
        # Keep a safety window to avoid using near-expiry tokens.
        return bool(self.access_token) and (self.expires_at_epoch - time()) > 60


def ebay_api_enabled() -> bool:
    return bool(settings.ebay_api_enabled)


def ebay_config_issue() -> str | None:
    if not settings.ebay_api_enabled:
        return "EBAY_API_ENABLED=false"

    if not settings.ebay_client_id.strip():
        return "EBAY_CLIENT_ID missing"

    if not settings.ebay_client_secret.strip():
        return "EBAY_CLIENT_SECRET missing"

    env = settings.ebay_env.strip().lower()
    if env not in {"production", "prod", "sandbox"}:
        return "EBAY_ENV must be production|sandbox"

    if not settings.ebay_marketplace_id.strip():
        return "EBAY_MARKETPLACE_ID missing"

    return None


def _is_sandbox() -> bool:
    return settings.ebay_env.strip().lower() == "sandbox"


def _identity_base_url() -> str:
    return "https://api.sandbox.ebay.com" if _is_sandbox() else "https://api.ebay.com"


def _api_base_url() -> str:
    return "https://api.sandbox.ebay.com" if _is_sandbox() else "https://api.ebay.com"


_cached_token: EbayAccessToken | None = None
_token_lock = asyncio.Lock()


async def get_ebay_access_token(*, force_refresh: bool = False) -> str:
    """Get OAuth application token (client-credentials).

    Token is cached in-process and refreshed shortly before expiry.
    """
    global _cached_token

    issue = ebay_config_issue()
    if issue:
        raise EbayConfigError(issue)

    if not force_refresh and _cached_token and _cached_token.is_valid:
        return _cached_token.access_token

    async with _token_lock:
        if not force_refresh and _cached_token and _cached_token.is_valid:
            return _cached_token.access_token

        token = await _request_new_token()
        _cached_token = token
        return token.access_token


async def _request_new_token() -> EbayAccessToken:
    token_url = f"{_identity_base_url()}/identity/v1/oauth2/token"
    basic = base64.b64encode(
        f"{settings.ebay_client_id}:{settings.ebay_client_secret}".encode("utf-8")
    ).decode("ascii")

    data = {
        "grant_type": "client_credentials",
        "scope": settings.ebay_oauth_scope.strip() or "https://api.ebay.com/oauth/api_scope",
    }

    retries = max(0, int(settings.ebay_max_retries))
    timeout = max(3.0, float(settings.ebay_request_timeout_s))

    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    token_url,
                    data=data,
                    headers={
                        "Authorization": f"Basic {basic}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )

            if resp.status_code in {429, 500, 502, 503, 504} and attempt < retries:
                await asyncio.sleep(0.6 * (attempt + 1))
                continue

            resp.raise_for_status()
            payload = resp.json()
            access_token = str(payload.get("access_token") or "").strip()
            expires_in = int(payload.get("expires_in") or 0)

            if not access_token or expires_in <= 0:
                raise EbayAPIError("eBay OAuth response missing access_token/expires_in")

            return EbayAccessToken(
                access_token=access_token,
                expires_at_epoch=time() + max(60, expires_in),
            )
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < retries:
                await asyncio.sleep(0.6 * (attempt + 1))
                continue

    raise EbayAPIError(f"Unable to fetch eBay OAuth token: {last_error}") from last_error


async def search_item_summaries(
    *,
    query: str,
    limit: int = 50,
) -> list[dict]:
    """Search listings through eBay Browse API.

    Returns raw itemSummaries objects from eBay API (empty list on no result).
    """
    issue = ebay_config_issue()
    if issue:
        raise EbayConfigError(issue)

    q = query.strip()
    if not q:
        return []

    safe_limit = max(1, min(200, int(limit)))
    retries = max(0, int(settings.ebay_max_retries))
    timeout = max(3.0, float(settings.ebay_request_timeout_s))

    last_error: Exception | None = None

    for attempt in range(retries + 1):
        force_refresh = attempt > 0
        try:
            token = await get_ebay_access_token(force_refresh=force_refresh)
            api_url = f"{_api_base_url()}/buy/browse/v1/item_summary/search"

            headers = {
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": settings.ebay_marketplace_id.strip() or "EBAY_DE",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            params = {
                "q": q,
                "limit": str(safe_limit),
            }

            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(api_url, headers=headers, params=params)

            if resp.status_code in {401, 403} and attempt < retries:
                # token expired/invalid/scope issue -> refresh and retry once.
                await asyncio.sleep(0.3 * (attempt + 1))
                continue

            if resp.status_code in {429, 500, 502, 503, 504} and attempt < retries:
                await asyncio.sleep(0.6 * (attempt + 1))
                continue

            resp.raise_for_status()
            payload = resp.json()
            rows = payload.get("itemSummaries")
            if not isinstance(rows, list):
                return []
            return [row for row in rows if isinstance(row, dict)]
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < retries:
                await asyncio.sleep(0.6 * (attempt + 1))
                continue

    raise EbayAPIError(f"eBay Browse search failed: {last_error}") from last_error


def redact_ebay_secret(raw: str) -> str:
    value = (raw or "").strip()
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"
