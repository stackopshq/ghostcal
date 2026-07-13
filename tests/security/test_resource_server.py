"""GhostAuth access-token validation, and the manifest's zero-knowledge invariant (no DB).

The token tests exercise the real ``jwt.decode`` path with a real key — only the JWKS fetch is
substituted. What is being pinned is the set of ways a resource server gets broken into:
algorithm confusion, a token from another issuer, a token for another audience, an expired one.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import jwt
import pytest
import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from ghostcal.infrastructure.security.resource_server import (
    GhostAuthValidator,
    TokenValidationError,
)
from ghostcal.presentation.portal_routes import _MANIFEST

ISSUER = "https://auth.ghost.local"
AUDIENCE = "ghostcal"
KID = "test-key"

_PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_JWK = jwt.algorithms.RSAAlgorithm.to_jwk(_PRIVATE.public_key(), as_dict=True)
_PUBLIC_JWK.update({"kid": KID, "use": "sig", "alg": "RS256"})
_JWKS = jwt.PyJWKSet.from_dict({"keys": [_PUBLIC_JWK]})


def _validator() -> GhostAuthValidator:
    validator = GhostAuthValidator(issuer=ISSUER, audience=AUDIENCE)

    async def _keys() -> jwt.PyJWKSet:
        return _JWKS

    validator._load_keys = _keys  # type: ignore[method-assign]
    return validator


def _token(**overrides: object) -> str:
    claims: dict[str, object] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "user-123",
        "exp": int(time.time()) + 300,
        "scope": "openid ghostsuite:ghostcal",
    }
    claims.update(overrides)
    return jwt.encode(claims, _PRIVATE, algorithm="RS256", headers={"kid": KID})


async def test_a_well_formed_token_is_accepted() -> None:
    claims = await _validator().verify(_token())
    assert claims["sub"] == "user-123"
    assert "ghostsuite:ghostcal" in claims["scope"]


async def test_a_token_from_another_issuer_is_rejected() -> None:
    forged = jwt.encode(
        {
            "iss": "https://evil.example",
            "aud": AUDIENCE,
            "sub": "user-123",
            "exp": int(time.time()) + 300,
        },
        _PRIVATE,
        algorithm="RS256",
        headers={"kid": KID},
    )
    with pytest.raises(TokenValidationError):
        await _validator().verify(forged)


async def test_a_token_for_another_audience_is_rejected() -> None:
    with pytest.raises(TokenValidationError):
        await _validator().verify(_token(aud="ghostmail"))


async def test_an_expired_token_is_rejected() -> None:
    with pytest.raises(TokenValidationError):
        await _validator().verify(_token(exp=int(time.time()) - 1))


async def test_a_token_with_no_expiry_is_rejected() -> None:
    """An access token that never expires is not an access token."""
    no_exp = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "sub": "user-123"},
        _PRIVATE,
        algorithm="RS256",
        headers={"kid": KID},
    )
    with pytest.raises(TokenValidationError):
        await _validator().verify(no_exp)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


async def test_algorithm_confusion_is_rejected() -> None:
    """The classic: HMAC-sign the token using the RSA *public* key as the shared secret.

    A verifier that trusts the token's own ``alg`` header would happily check that signature — the
    public key is public — and let the forgery through. Pinning an asymmetric allow-list is what
    makes it impossible, which is why the list is fixed rather than read off the header.

    The token is assembled by hand: PyJWT's ``encode`` refuses to HMAC-sign with a PEM public key,
    which protects the *signer*. An attacker is not using our library.
    """
    public_pem = _PRIVATE.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": KID}).encode())
    payload = _b64(
        json.dumps(
            {
                "iss": ISSUER,
                "aud": AUDIENCE,
                "sub": "user-123",
                "exp": int(time.time()) + 300,
            }
        ).encode()
    )
    signing_input = f"{header}.{payload}".encode()
    signature = _b64(hmac.new(public_pem, signing_input, hashlib.sha256).digest())
    forged = f"{header}.{payload}.{signature}"

    with pytest.raises(TokenValidationError):
        await _validator().verify(forged)


def test_the_manifest_declares_no_widget_the_server_could_not_honestly_fill() -> None:
    """The zero-knowledge invariant, pinned.

    GhostCal's server holds event and task titles as ciphertext sealed to a key it does not have. A
    ``list`` widget would have to carry titles — so declaring one would mean either lying to the
    portal or having quietly stopped encrypting. Only ``stat`` (a count) is honest here, and this
    test is what makes adding a list widget a deliberate act rather than an oversight.
    """
    manifest = yaml.safe_load(_MANIFEST.read_text(encoding="utf-8"))

    kinds = {w["kind"] for w in manifest["spec"]["widgets"]}
    assert kinds == {"stat"}, f"a zero-knowledge app cannot serve {kinds - {'stat'}} widgets"

    # The portal's CSP blocks cross-origin images, so it keeps its own icon: we must not send one.
    assert "icon" not in manifest["metadata"]

    assert manifest["metadata"]["id"] == "ghostcal"
    assert manifest["spec"]["auth"]["required_scopes"] == ["ghostsuite:ghostcal"]
