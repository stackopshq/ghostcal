"""Share when you are free, without showing what you are doing.

The last of the GhostMail hooks, and the cheapest — because there is nothing to encrypt.

:mod:`ghostcal.application.links` (ADR-0009) shares a *calendar*: the events are sealed, so the link
must carry a key, and that key rides in the URL fragment where the server can never see it. All of
that machinery exists because the content is secret.

A free-busy link shares no content. It answers one question — *when is this person occupied?* — and
the answer is **already cleartext on the server**: the scheduler has to reason about busy time to
offer slots at all. So there is nothing to seal, nothing to hand over, and no key.

Which makes the security story simple, and worth saying plainly: a busy link discloses strictly what
the server already knows. Whoever finds the token learns *when* the owner is occupied, and never
once *what* occupies them. A different bargain from an ADR-0009 link, and a much smaller one.

The busy times themselves come from :func:`ghostcal.application.scheduling.busy_for` — the same
function the booking page uses. Not a copy of it. If the two ever disagreed, one of them would be
lying to someone.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BusyLinkRecord:
    id: uuid.UUID
    name: str
    created_at: datetime


@dataclass(frozen=True)
class BusyLinkOwner:
    """Who a token belongs to. Resolved without any RLS context — the visitor has none."""

    organization_id: uuid.UUID
    user_id: uuid.UUID
    owner_name: str
    owner_timezone: str


class BusyLinkRepository:
    async def create(self, user_id: uuid.UUID, *, token_hash: str, name: str) -> uuid.UUID:
        raise NotImplementedError

    async def list_for_user(self, user_id: uuid.UUID) -> list[BusyLinkRecord]:
        raise NotImplementedError

    async def delete(self, user_id: uuid.UUID, link_id: uuid.UUID) -> bool:
        raise NotImplementedError

    async def resolve(self, token_hash: str) -> BusyLinkOwner | None:
        """Token → the person it belongs to. The visitor's only door, and it leads to one person."""
        raise NotImplementedError
