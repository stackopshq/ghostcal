"""CalDAV connection management and busy-sync use cases (host dashboard).

A member may connect **several** external calendars — work, personal, a shared family one. That is
ordinary for a calendar client, and it is why everything here is keyed by *connection*, not by user.

Two things stop being obvious once there is more than one calendar, and both are decided rather than
left to whichever code path happens to run first:

- bookings mirror onto **one** calendar (``mirror_bookings``), because writing each meeting to every
  connected calendar would duplicate it;
- each connection carries its own **colour**, so it is its own overlay in the calendar rather than
  vanishing into a single anonymous "External" bucket.
"""

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
    """No such connection for this user."""


class TooManyConnections(Exception):
    """A cap on connected calendars — each one is a credential we hold and a URL we poll."""


# Enough for work + personal + family + a spare, and low enough that a runaway client cannot turn an
# account into a crawler pointed at someone else's server.
MAX_CONNECTIONS = 8

# Cycled through when connecting a calendar, so two accounts do not land on the same overlay colour.
PALETTE = ("#7aa2f7", "#bb9af7", "#7dcfff", "#9ece6a", "#e0af68", "#f7768e", "#2ac3de", "#c0caf5")


@dataclass(frozen=True, slots=True)
class ConnectionRecord:
    id: uuid.UUID
    user_id: uuid.UUID
    server_url: str
    username: str
    password_encrypted: str
    calendar_url: str
    calendar_name: str | None
    color: str
    mirror_bookings: bool
    status: str
    last_synced_at: datetime | None


class SecretCipher(Protocol):
    """Encrypts/decrypts a secret (implemented by the Fernet SecretBox)."""

    def encrypt(self, plaintext: str) -> str: ...

    def decrypt(self, token: str) -> str: ...


class CaldavConnectionRepository:
    async def list_for_user(self, user_id: uuid.UUID) -> list[ConnectionRecord]:
        raise NotImplementedError

    async def get(self, connection_id: uuid.UUID, user_id: uuid.UUID) -> ConnectionRecord | None:
        raise NotImplementedError

    async def mirror_target(self, user_id: uuid.UUID) -> ConnectionRecord | None:
        """The one calendar bookings are written back to, if any."""
        raise NotImplementedError

    async def create(
        self,
        user_id: uuid.UUID,
        *,
        server_url: str,
        username: str,
        password_encrypted: str,
        calendar_url: str,
        calendar_name: str | None,
        color: str,
        mirror_bookings: bool,
    ) -> uuid.UUID:
        raise NotImplementedError

    async def delete(self, connection_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        raise NotImplementedError

    async def set_mirror_target(self, connection_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Make this the calendar bookings mirror onto, clearing whichever one was."""
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


async def list_connections(
    repo: CaldavConnectionRepository, user_id: uuid.UUID
) -> list[ConnectionRecord]:
    return await repo.list_for_user(user_id)


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
    """Connect another external calendar.

    The first one connected becomes the booking mirror target — with nothing else to be, it is the
    only sensible default; the user can move it afterwards. Later ones do not, because silently
    re-pointing where a host's meetings are written is not a thing to do on their behalf.
    """
    existing = await repo.list_for_user(user_id)
    if len(existing) >= MAX_CONNECTIONS:
        raise TooManyConnections(f"at most {MAX_CONNECTIONS} calendars can be connected")

    return await repo.create(
        user_id,
        server_url=server_url,
        username=username,
        password_encrypted=cipher.encrypt(password),
        calendar_url=calendar_url,
        calendar_name=calendar_name,
        color=PALETTE[len(existing) % len(PALETTE)],
        mirror_bookings=not existing,
    )


async def disconnect_calendar(
    repo: CaldavConnectionRepository, connection_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    if not await repo.delete(connection_id, user_id):
        raise NotConnected()


async def choose_mirror_target(
    repo: CaldavConnectionRepository, connection_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    if not await repo.set_mirror_target(connection_id, user_id):
        raise NotConnected()


async def sync_connection(
    repo: CaldavConnectionRepository,
    cipher: SecretCipher,
    client: CalendarClient,
    clock: Clock,
    *,
    connection_id: uuid.UUID,
    user_id: uuid.UUID,
    window_days: int = 60,
) -> int:
    """Pull one connection's busy intervals into ``external_busy``. Returns how many synced."""
    record = await repo.get(connection_id, user_id)
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


async def sync_all_for_user(
    repo: CaldavConnectionRepository,
    cipher: SecretCipher,
    client: CalendarClient,
    clock: Clock,
    *,
    user_id: uuid.UUID,
    window_days: int = 60,
) -> int:
    """Sync every calendar the user has connected. One failing account does not stop the others —
    a stale password on the work calendar must not silently freeze the personal one."""
    synced = 0
    for record in await repo.list_for_user(user_id):
        try:
            synced += await sync_connection(
                repo,
                cipher,
                client,
                clock,
                connection_id=record.id,
                user_id=user_id,
                window_days=window_days,
            )
        except CalendarAuthError, NotConnected:
            continue
    return synced
