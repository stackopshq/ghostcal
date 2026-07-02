"""OIDC provider wiring (Authlib + Starlette).

A single operator-configured provider. Discovery, token exchange and ID-token validation (JWKS,
issuer, audience, expiry, nonce) are delegated to Authlib; PKCE (S256) is enabled. The client
secret lives only here, server-side. This handles *authentication* only — the zero-knowledge
content is unlocked separately by an encryption passphrase the server never sees.
"""

from __future__ import annotations

from functools import lru_cache

from authlib.integrations.starlette_client import OAuth, StarletteOAuth2App

from ghostcal.config import get_settings

_CLIENT_NAME = "ghostcal_oidc"


class OIDCNotConfigured(Exception):
    """OIDC was requested but is disabled or missing configuration."""


@lru_cache
def _oauth() -> OAuth:
    settings = get_settings()
    if not settings.oidc_enabled:
        raise OIDCNotConfigured("OIDC is disabled")
    if not (settings.oidc_issuer and settings.oidc_client_id and settings.oidc_client_secret):
        raise OIDCNotConfigured("OIDC issuer/client_id/client_secret are not all set")
    oauth = OAuth()
    oauth.register(
        name=_CLIENT_NAME,
        server_metadata_url=f"{settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration",
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret.get_secret_value(),
        client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
    )
    return oauth


def oidc_client() -> StarletteOAuth2App:
    """The registered OIDC client, or raise ``OIDCNotConfigured`` when unavailable."""
    client = _oauth().create_client(_CLIENT_NAME)
    if client is None:  # pragma: no cover - registration guarantees this
        raise OIDCNotConfigured("OIDC client is not registered")
    return client
