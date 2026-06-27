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


class BookingManagementCodec:
    """Stateless, signed token letting an invitee manage their booking (no account).

    Encodes the booking and organization ids; verified by signature. No expiry — it stays valid
    until the booking is cancelled/rescheduled (operations check the booking status).
    """

    def __init__(self, secret: str) -> None:
        self._secret = secret

    def encode(self, booking_id: uuid.UUID, organization_id: uuid.UUID) -> str:
        payload = {"bid": str(booking_id), "oid": str(organization_id), "purpose": "manage"}
        return jwt.encode(payload, self._secret, algorithm=_ALGORITHM)

    def decode(self, token: str) -> tuple[uuid.UUID, uuid.UUID]:
        try:
            payload = jwt.decode(token, self._secret, algorithms=[_ALGORITHM])
            if payload.get("purpose") != "manage":
                raise ValueError("wrong token purpose")
            return uuid.UUID(payload["bid"]), uuid.UUID(payload["oid"])
        except (jwt.PyJWTError, KeyError, ValueError) as exc:
            raise ValueError("invalid management token") from exc
