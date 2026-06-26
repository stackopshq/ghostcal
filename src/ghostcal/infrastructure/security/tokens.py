"""JWT access-token codec (HS256)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt

_ALGORITHM = "HS256"


class JwtAccessTokenCodec:
    def __init__(self, secret: str, ttl: timedelta) -> None:
        self._secret = secret
        self._ttl = ttl

    def encode(self, user_id: uuid.UUID) -> str:
        now = datetime.now(UTC)
        payload = {"sub": str(user_id), "iat": now, "exp": now + self._ttl}
        return jwt.encode(payload, self._secret, algorithm=_ALGORITHM)

    def decode(self, token: str) -> uuid.UUID:
        try:
            payload = jwt.decode(token, self._secret, algorithms=[_ALGORITHM])
            return uuid.UUID(payload["sub"])
        except (jwt.PyJWTError, KeyError, ValueError) as exc:
            raise ValueError("invalid access token") from exc
