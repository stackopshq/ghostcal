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


class AccessTokenCodec(Protocol):
    def encode(self, user_id: uuid.UUID) -> str: ...

    def decode(self, token: str) -> uuid.UUID:
        """Return the subject user id. Raise ``ValueError`` if invalid or expired."""
        ...
