from __future__ import annotations

from functools import lru_cache

import jwt
from jwt import InvalidTokenError

from app.core.config import settings


class ExternalAuthError(Exception):
    pass


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url)


def verify_external_jwt(token: str) -> dict:
    issuer = settings.auth_issuer.strip()
    audience = settings.auth_audience.strip()
    jwks_url = settings.auth_jwks_url.strip()

    if not jwks_url:
        raise ExternalAuthError("external auth misconfigured: AUTH_JWKS_URL missing")

    try:
        signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token).key
        decode_kwargs: dict = {
            "algorithms": ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
            "options": {"require": ["exp", "iat"]},
        }
        if audience:
            decode_kwargs["audience"] = audience
        else:
            decode_kwargs["options"]["verify_aud"] = False

        if issuer:
            decode_kwargs["issuer"] = issuer

        claims = jwt.decode(token, signing_key, **decode_kwargs)
    except InvalidTokenError as exc:
        raise ExternalAuthError(f"invalid token: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ExternalAuthError(f"external auth validation failed: {exc}") from exc

    return claims
