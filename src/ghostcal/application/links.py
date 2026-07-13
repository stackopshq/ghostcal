"""Share a calendar outside the organization, by secret link. See ADR-0009.

ADR-0005 parked this with: sharing beyond the org "would require granting them the org key — that
reuses the invitation-fragment grant (ADR-0003) and is deferred."

**That path is wrong, not merely deferred.** The org key opens ``bookings.invitee_private`` (every
invitee's answers, across the whole organization), ``calendar_events.content`` (every calendar of
every member) and ``tasks.content``. Handing it to an outsider so they can see *one* calendar would
hand them the encrypted contents of the entire organization. It is worth writing down, because the
shortcut is right there and it looks reasonable.

So a link carries **its own keypair**:

- the **public** key is stored (a public key is public);
- the **private** key never reaches the server — it lives in the URL fragment, which browsers do not
  transmit. The same move ghostbit makes, and ADR-0003 already makes here.

The owner's browser seals a copy of each event to the link's public key. The visitor's browser opens
those copies with the private key it read out of the fragment. The server holds a second envelope it
cannot open, next to the first envelope it cannot open.

Sealing a *new* event later needs only the public key, which is why this is a keypair and not a
shared symmetric key: the owner never has to keep the link's secret anywhere.

Whoever has the link has the calendar. That is the bargain — the same one ghostbit makes — and
revocation is deleting the link.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime


class LinkError(Exception):
    """Base class for link errors."""


class CalendarNotFound(LinkError):
    pass


class LinkNotFound(LinkError):
    pass


def new_token() -> str:
    """The token that goes in the URL path. Shown to the owner once; only its hash is stored."""
    return secrets.token_urlsafe(32)


def hash_token(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


@dataclass(frozen=True)
class LinkRecord:
    id: uuid.UUID
    calendar_id: uuid.UUID
    name: str
    public_key: str
    created_at: datetime
    # How many events on the calendar still have no sealed copy for this link — i.e. what the
    # owner's browser has left to do. Zero means the link shows the whole calendar.
    pending: int


@dataclass(frozen=True)
class SealedCopy:
    """An event's content, re-sealed by the owner's browser to the link's public key."""

    event_id: uuid.UUID
    content_sealed: str


@dataclass(frozen=True)
class PendingSeal:
    """An event a link has no readable copy of yet. ``content`` is still sealed to the ORG key —
    the owner's browser opens it with that, and re-seals it to the link's public key."""

    event_id: uuid.UUID
    content: str | None


@dataclass(frozen=True)
class PublicEvent:
    """What a visitor gets. ``content_sealed`` opens with the key from the fragment, and nothing
    else on the server does."""

    start_at: datetime
    end_at: datetime
    all_day: bool
    timezone: str
    rrule: str | None
    exdates: list[str]
    content_sealed: str


@dataclass(frozen=True)
class PublicCalendar:
    calendar_name: str
    owner_name: str
    events: list[PublicEvent]


class LinkRepository:
    async def create(
        self,
        owner_id: uuid.UUID,
        calendar_id: uuid.UUID,
        *,
        token_hash: str,
        public_key: str,
        name: str,
    ) -> uuid.UUID | None:
        """Create a link on the owner's calendar. None if it is not theirs."""
        raise NotImplementedError

    async def list_for_calendar(
        self, owner_id: uuid.UUID, calendar_id: uuid.UUID
    ) -> list[LinkRecord]:
        raise NotImplementedError

    async def delete(self, owner_id: uuid.UUID, link_id: uuid.UUID) -> bool:
        raise NotImplementedError

    async def pending_seals(
        self, owner_id: uuid.UUID, link_id: uuid.UUID, *, limit: int
    ) -> list[PendingSeal]:
        """Events this link has no sealed copy of yet — still sealed to the org key."""
        raise NotImplementedError

    async def store_copies(
        self, owner_id: uuid.UUID, link_id: uuid.UUID, copies: list[SealedCopy]
    ) -> int:
        raise NotImplementedError

    async def public_calendar(self, token_hash: str) -> PublicCalendar | None:
        """The visitor's view: one calendar's sealed copies, and nothing else in the system."""
        raise NotImplementedError
