"""Symmetric encryption for secrets at rest (e.g. CalDAV passwords).

A Fernet key is derived from the configured ``token_encryption_key`` via SHA-256 so any 32+ char
secret works. Fernet gives authenticated encryption (AES-128-CBC + HMAC).
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet


def _fernet(secret: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


class SecretBox:
    def __init__(self, secret: str) -> None:
        self._fernet = _fernet(secret)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode("ascii")

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode("ascii")).decode()
