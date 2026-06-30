"""Transparent at-rest encryption for sensitive columns.

These ``TypeDecorator``s envelope-encrypt values with the application key (the same
``SecretBox`` used for CalDAV passwords) on the way to the database and decrypt them on the way
back, so application and repository code keep handling plaintext. A stolen database dump reveals
no invitee emails, guest lists or meeting links — only ciphertext. See ADR-0002.

This is encryption *at rest*, not zero-knowledge: the server holds the key and can decrypt (it
must, to send reminder emails days later). The invitee's answers, notes and name are protected by
the stronger zero-knowledge sealed blob (``bookings.invitee_private``), which the server can never
read. Slot times stay cleartext — they are the backbone of the no-double-booking ``EXCLUDE``
constraint and cannot be encrypted without losing that guarantee.
"""

from __future__ import annotations

import json
from functools import cache

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from ghostcal.config import get_settings
from ghostcal.infrastructure.security.encryption import SecretBox


@cache
def _cipher() -> SecretBox:
    return SecretBox(get_settings().token_encryption_key.get_secret_value())


class EncryptedString(TypeDecorator[str]):
    """A text column encrypted at rest with the application key."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: object) -> str | None:
        return None if value is None else _cipher().encrypt(value)

    def process_result_value(self, value: str | None, dialect: object) -> str | None:
        return None if value is None else _cipher().decrypt(value)


class EncryptedStringList(TypeDecorator[list]):  # type: ignore[type-arg]
    """A ``list[str]`` stored as one encrypted JSON blob (e.g. additional guest emails)."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: list[str] | None, dialect: object) -> str | None:
        if value is None:
            return None
        return _cipher().encrypt(json.dumps(list(value)))

    def process_result_value(self, value: str | None, dialect: object) -> list[str]:
        if value is None:
            return []
        decoded = json.loads(_cipher().decrypt(value))
        return [str(item) for item in decoded]
