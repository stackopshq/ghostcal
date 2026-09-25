"""Security ports: password hashing, access-token encoding, TOTP.

Implemented in the infrastructure layer (Argon2, JWT, pyotp). The use cases depend only on these
interfaces, so they can be unit-tested with trivial fakes.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, hashed: str, password: str) -> bool: ...


class BreachedPasswordChecker(Protocol):
    async def is_breached(self, password: str) -> bool:
        """True if the password is known to appear in a public breach corpus.

        Implementations must fail *open* — return False when the check cannot be performed. A
        password-strength advisory that can lock people out of registering when a third party is
        having a bad day is a worse problem than the one it solves.
        """
        ...


class AccessTokenCodec(Protocol):
    def encode(self, user_id: uuid.UUID) -> str: ...

    def decode(self, token: str) -> uuid.UUID:
        """Return the subject user id. Raise ``ValueError`` if invalid or expired."""
        ...


class TotpEngine(Protocol):
    """RFC 6238, derrière une interface, pour que les cas d'usage se testent sans horloge réelle."""

    def new_secret(self) -> str:
        """Une graine base32 neuve."""
        ...

    def provisioning_uri(self, secret: str, *, account: str) -> str:
        """L'URI ``otpauth://`` à présenter en QR code."""
        ...

    def verify(self, secret: str, code: str, *, at: datetime) -> int | None:
        """La **période** qui correspond au code, ou ``None``.

        Rendre la période et non un booléen est ce qui rend l'anti-rejeu
        possible : l'appelant compare ce numéro à la dernière période consommée.
        Un booléen ne permettrait que de dire « ce code est valide », jamais
        « ce code a déjà servi ».
        """
        ...
