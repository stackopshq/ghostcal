"""Argon2id password hashing (the OWASP-recommended default)."""

from __future__ import annotations

from argon2 import PasswordHasher as _Argon2
from argon2.exceptions import InvalidHashError, VerificationError


class Argon2PasswordHasher:
    def __init__(self) -> None:
        self._ph = _Argon2()

    def hash(self, password: str) -> str:
        return self._ph.hash(password)

    def verify(self, hashed: str, password: str) -> bool:
        # VerificationError covers a wrong password; InvalidHashError a malformed stored hash.
        try:
            return self._ph.verify(hashed, password)
        except VerificationError, InvalidHashError:
            return False
