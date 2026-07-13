"""GhostAuth access-token validation — the resource-server side of the suite.

GhostCal is already an OIDC *client* for interactive login (``oidc.py``). This is the complementary
*resource-server* piece: it validates access tokens minted by GhostAuth, so the ghostboard portal
can call GhostCal's widget endpoints on a user's behalf by forwarding that user's
``Authorization: Bearer``.

Deliberately narrow. It is mounted only on the portal-facing routes; GhostCal's own UI and API keep
their local sessions and their own bearer. Two token systems, no overlap.

Validation: signature against the IdP's JWKS, with an allow-list of asymmetric algorithms — pinning
it is what stops algorithm confusion, and it is why ``alg: none`` and any HMAC variant are rejected
outright rather than merely failing to verify. Then issuer, audience and expiry.

Unlike the sibling apps, this needs no new dependency: PyJWT is already here and does RS256, ES256
and EdDSA. It has a JWKS client of its own, but a synchronous one, so the fetch is done with the
httpx we already use and the keys are built from the JWK documents directly.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import jwt
from jwt import PyJWK, PyJWKSet

from ghostcal.config import get_settings

# GhostAuth signs per realm with one of these. The allow-list is the point: without it, a token
# claiming `alg: HS256` could be "verified" against the public key as if it were a shared secret.
_ACCEPTED_ALGORITHMS = ("RS256", "ES256", "EdDSA")
_JWKS_TTL_SECONDS = 3600
_HTTP_TIMEOUT = 5.0


class TokenValidationError(Exception):
    """The presented bearer is not a valid GhostAuth access token."""


class ResourceServerNotConfigured(RuntimeError):
    """Portal token validation was asked for, but the issuer/audience are not set."""


class GhostAuthValidator:
    """Validates GhostAuth access tokens, caching discovery and the JWKS."""

    def __init__(self, *, issuer: str, audience: str) -> None:
        self._issuer = issuer.rstrip("/")
        self._audience = audience
        self._jwks_uri: str | None = None
        self._keys: PyJWKSet | None = None
        self._expiry = 0.0

    async def _load_keys(self) -> PyJWKSet:
        now = time.time()
        if self._keys is not None and now < self._expiry:
            return self._keys
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            if self._jwks_uri is None:
                meta = await client.get(f"{self._issuer}/.well-known/openid-configuration")
                meta.raise_for_status()
                self._jwks_uri = meta.json()["jwks_uri"]
            response = await client.get(self._jwks_uri)
            response.raise_for_status()
            self._keys = PyJWKSet.from_dict(response.json())
            self._expiry = now + _JWKS_TTL_SECONDS
        return self._keys

    def _signing_key(self, keys: PyJWKSet, token: str) -> PyJWK:
        kid = jwt.get_unverified_header(token).get("kid")
        for key in keys.keys:
            if kid is None or key.key_id == kid:
                return key
        raise TokenValidationError("no JWKS key matches the token's kid")

    async def verify(self, token: str) -> dict[str, Any]:
        """The validated claims, or ``TokenValidationError``."""
        try:
            keys = await self._load_keys()
        except (httpx.HTTPError, KeyError, jwt.PyJWKSetError) as exc:
            raise TokenValidationError("cannot load the GhostAuth JWKS") from exc

        try:
            key = self._signing_key(keys, token)
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key.key,
                algorithms=list(_ACCEPTED_ALGORITHMS),
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["exp", "iss", "aud"]},
            )
        except jwt.InvalidTokenError as exc:
            raise TokenValidationError(f"token rejected: {exc}") from exc
        return claims


_validator: GhostAuthValidator | None = None


def get_ghostauth_validator() -> GhostAuthValidator:
    """Build the validator once, from settings.

    The audience defaults to the OIDC client id — the common case, where GhostAuth mints access
    tokens whose ``aud`` is the requesting client. Set ``GHOSTCAL_OIDC_AUDIENCE`` when the realm
    issues a distinct resource identifier instead.
    """
    global _validator
    if _validator is not None:
        return _validator
    settings = get_settings()
    audience = settings.oidc_audience or settings.oidc_client_id
    if not settings.oidc_issuer or not audience:
        raise ResourceServerNotConfigured(
            "portal token validation needs oidc_issuer and oidc_audience (or oidc_client_id)"
        )
    _validator = GhostAuthValidator(issuer=settings.oidc_issuer, audience=audience)
    return _validator


def reset_validator_cache() -> None:
    """Test hook: drop the cached validator so a settings change takes effect."""
    global _validator
    _validator = None
