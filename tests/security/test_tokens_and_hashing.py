"""Unit tests for the security adapters (no DB)."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from ghostcal.infrastructure.security.passwords import Argon2PasswordHasher
from ghostcal.infrastructure.security.tokens import JwtAccessTokenCodec


def test_argon2_hash_and_verify() -> None:
    hasher = Argon2PasswordHasher()
    hashed = hasher.hash("correct horse battery staple")
    assert hashed != "correct horse battery staple"  # not stored in clear
    assert hasher.verify(hashed, "correct horse battery staple") is True
    assert hasher.verify(hashed, "wrong password") is False


def test_argon2_rejects_garbage_hash() -> None:
    assert Argon2PasswordHasher().verify("not-a-real-hash", "whatever") is False


def test_jwt_roundtrip() -> None:
    codec = JwtAccessTokenCodec("a-secret-of-at-least-32-characters!!", timedelta(minutes=15))
    user_id = uuid.uuid4()
    token = codec.encode(user_id)
    assert codec.decode(token) == user_id


def test_jwt_rejects_tampered_and_expired() -> None:
    codec = JwtAccessTokenCodec("a-secret-of-at-least-32-characters!!", timedelta(minutes=15))
    with pytest.raises(ValueError):
        codec.decode("garbage.token.value")
    # Wrong secret.
    other = JwtAccessTokenCodec("a-different-secret-of-32-characters!!", timedelta(minutes=15))
    with pytest.raises(ValueError):
        other.decode(codec.encode(uuid.uuid4()))
    # Already expired.
    expired = JwtAccessTokenCodec("a-secret-of-at-least-32-characters!!", timedelta(minutes=-1))
    with pytest.raises(ValueError):
        codec.decode(expired.encode(uuid.uuid4()))
