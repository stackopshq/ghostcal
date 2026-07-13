"""Publish a calendar to an external CalDAV server — without the server ever reading an event.

The obvious way to sync a calendar out is to let the server read the events and push them on a
schedule. That works, and it is the end of zero-knowledge for those calendars. So it is not what
this does.

**The server relays cleartext and never stores it.** Only the browser holds the org key, so only the
browser can turn a sealed event into a VEVENT. It does that, hands the cleartext over at push time,
and the server forwards it to the CalDAV server and writes none of it down. The pattern is already
in this codebase: event invitations build their ICS from browser-supplied cleartext at send time and
persist nothing.

The cost, stated plainly: **a push waits for a browser.** There is no background reconciliation,
because nothing in the background can read an event. That is why there is a queue rather than a
worker: a write marks the event as needing a push, and the next tab that opens with the key unlocked
drains it. The tab does not have to be open when the change happens — only at some point afterwards.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

PushOp = Literal["upsert", "delete"]

# How many queued items a browser is handed at once. Each one is a round-trip to somebody else's
# CalDAV server, so a batch that is too eager just makes the request time out.
BATCH = 25


class PushError(Exception):
    """Base class for publication errors."""


class NotPublished(PushError):
    """That calendar publishes nowhere, so there is nothing to push it to."""


@dataclass(frozen=True)
class PendingPush:
    """One thing to publish. For an upsert, ``content`` is still SEALED — the browser opens it."""

    id: uuid.UUID
    op: PushOp
    external_uid: str
    # Everything below is NULL for a delete: the event is gone, and only the UID is needed to remove
    # it from the far end.
    content: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    all_day: bool = False
    rrule: str | None = None


@dataclass(frozen=True)
class ResolvedPush:
    """The same thing, opened in the browser. This is the only place cleartext exists server-side,
    and it exists in memory for exactly as long as the CalDAV request takes."""

    id: uuid.UUID
    op: PushOp
    external_uid: str
    summary: str = ""
    description: str = ""
    location: str = ""
    start_at: datetime | None = None
    end_at: datetime | None = None
    rrule: str | None = None


@dataclass(frozen=True)
class PushTarget:
    """Where a calendar publishes to."""

    calendar_id: uuid.UUID
    connection_id: uuid.UUID
    server_url: str
    username: str
    password_encrypted: str
    calendar_url: str


class PushRepository:
    async def set_target(
        self, owner_id: uuid.UUID, calendar_id: uuid.UUID, connection_id: uuid.UUID | None
    ) -> bool:
        """Publish this calendar to that connected calendar, or nowhere. False if not theirs."""
        raise NotImplementedError

    async def backfill(self, calendar_id: uuid.UUID) -> int:
        """Queue everything already on the calendar. Publishing must push what is there, not only
        what changes next."""
        raise NotImplementedError

    async def pending(self, owner_id: uuid.UUID, *, limit: int) -> list[PendingPush]:
        raise NotImplementedError

    async def target_for(self, owner_id: uuid.UUID, queue_id: uuid.UUID) -> PushTarget | None:
        raise NotImplementedError

    async def done(self, owner_id: uuid.UUID, queue_id: uuid.UUID) -> None:
        """Drop a queue row once its CalDAV write has actually landed."""
        raise NotImplementedError
