"""CalDAV connection management and busy-sync use cases (host dashboard)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from ghostcal.application.ports.calendar import (
    BusyEvent,
    CalendarAuthError,
    CalendarClient,
    CalendarCredentials,
    CalendarInfo,
)
from ghostcal.application.ports.clock import Clock


class NotConnected(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ConnectionRecord:
    id: uuid.UUID
    user_id: uuid.UUID
    server_url: str
    username: str
    password_encrypted: str
    calendar_url: str
    calendar_name: str | None
    status: str
    last_synced_at: datetime | None


class SecretCipher(Protocol):
    """Encrypts/decrypts a secret (implemented by the Fernet SecretBox)."""

    def encrypt(self, plaintext: str) -> str: ...

    def decrypt(self, token: str) -> str: ...


class CaldavConnectionRepository:
    async def get(self, user_id: uuid.UUID) -> ConnectionRecord | None:
        raise NotImplementedError

    async def save(
        self,
        user_id: uuid.UUID,
        *,
        server_url: str,
        username: str,
        password_encrypted: str,
        calendar_url: str,
        calendar_name: str | None,
    ) -> uuid.UUID:
        raise NotImplementedError

    async def delete(self, user_id: uuid.UUID) -> bool:
        raise NotImplementedError

    async def replace_busy(
        self, connection_id: uuid.UUID, host_id: uuid.UUID, busy: list[BusyEvent]
    ) -> None:
        raise NotImplementedError

    async def mark_synced(self, connection_id: uuid.UUID, when: datetime, status: str) -> None:
        raise NotImplementedError


async def list_available_calendars(
    client: CalendarClient, *, server_url: str, username: str, password: str
) -> list[CalendarInfo]:
    return await client.list_calendars(
        CalendarCredentials(server_url=server_url, username=username, password=password)
    )


async def connect_calendar(
    repo: CaldavConnectionRepository,
    cipher: SecretCipher,
    *,
    user_id: uuid.UUID,
    server_url: str,
    username: str,
    password: str,
    calendar_url: str,
    calendar_name: str | None,
) -> uuid.UUID:
    return await repo.save(
        user_id,
        server_url=server_url,
        username=username,
        password_encrypted=cipher.encrypt(password),
        calendar_url=calendar_url,
        calendar_name=calendar_name,
    )


async def disconnect_calendar(repo: CaldavConnectionRepository, user_id: uuid.UUID) -> None:
    await repo.delete(user_id)


async def sync_calendar(
    repo: CaldavConnectionRepository,
    cipher: SecretCipher,
    client: CalendarClient,
    clock: Clock,
    *,
    user_id: uuid.UUID,
    window_days: int = 60,
) -> int:
    """Pull busy intervals into ``external_busy``. Returns the number of busy blocks synced."""
    record = await repo.get(user_id)
    if record is None:
        raise NotConnected()

    creds = CalendarCredentials(
        server_url=record.server_url,
        username=record.username,
        password=cipher.decrypt(record.password_encrypted),
    )
    now = clock.now()
    try:
        busy = await client.fetch_busy(
            creds, record.calendar_url, now, now + timedelta(days=window_days)
        )
    except CalendarAuthError:
        await repo.mark_synced(record.id, now, status="needs_reauth")
        raise

    await repo.replace_busy(record.id, user_id, busy)
    await repo.mark_synced(record.id, now, status="active")
    return len(busy)
