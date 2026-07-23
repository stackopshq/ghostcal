"""Security ports: password hashing and access-token encoding.

Implemented in the infrastructure layer (Argon2, JWT). The use cases depend only on these
interfaces, so they can be unit-tested with trivial fakes.
"""

from __future__ import annotations

import uuid
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
