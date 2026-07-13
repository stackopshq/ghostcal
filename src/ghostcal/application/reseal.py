"""Re-sealing the backlog after a rotation (ADR-0007) — where revocation becomes total.

Rotating the org key stops the leak going forward: everything created afterwards is sealed to a key
the departed member never had. What it does not do is take back the records sealed *before* — those
are still readable with the key they kept.

This pass closes that. In the admin's browser (the only place both keys exist), each record still
sealed under an older generation is opened with the key that sealed it and re-sealed to the current
one. When the backlog reaches zero, the old key opens nothing at all.

Three properties it has to have, because this walks over the organization's entire encrypted
history:

- **resumable.** It runs in a browser, over a possibly large backlog. Closing the tab must cost
  progress, not correctness.
- **idempotent.** A retried batch must be a no-op, not a corruption. The write is filtered on the
  row still being behind, so re-applying it changes nothing.
- **refused if the ground moves.** If the org rotates again mid-pass, blobs sealed to the previous
  key are already stale; writing them would stamp them as current and quietly strand them. The
  caller says which generation it sealed to, and a mismatch is refused rather than written.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

SealedKind = Literal["booking", "event", "task"]


class ResealError(Exception):
    """Base class for re-sealing errors."""


class NotAuthorized(ResealError):
    """Only an owner or an admin may re-seal an organization's backlog."""


class RotatedUnderneath(ResealError):
    """The org key rotated again while this pass was running. The blobs in hand are stale."""


@dataclass(frozen=True)
class PendingRecord:
    """A record still sealed under an older generation. ``sealed`` is ciphertext, as always."""

    kind: SealedKind
    id: uuid.UUID
    sealed: str


@dataclass(frozen=True)
class ResealedRecord:
    """The same record, opened and re-sealed to the current key — in the browser, never here."""

    kind: SealedKind
    id: uuid.UUID
    sealed: str


@dataclass(frozen=True)
class Backlog:
    """How much of the organization's history is still sealed under a retired key."""

    generation: int
    remaining: int


class ResealRepository:
    async def backlog(self, organization_id: uuid.UUID) -> Backlog:
        raise NotImplementedError

    async def pending(self, organization_id: uuid.UUID, *, limit: int) -> list[PendingRecord]:
        raise NotImplementedError

    async def apply(
        self,
        organization_id: uuid.UUID,
        *,
        generation: int,
        records: list[ResealedRecord],
    ) -> int:
        """Write the re-sealed blobs back. Returns how many rows actually moved."""
        raise NotImplementedError


class ResealService:
    def __init__(self, repo: ResealRepository) -> None:
        self._repo = repo

    async def backlog(self, organization_id: uuid.UUID) -> Backlog:
        return await self._repo.backlog(organization_id)

    async def pending(self, organization_id: uuid.UUID, *, limit: int) -> list[PendingRecord]:
        return await self._repo.pending(organization_id, limit=limit)

    async def apply(
        self,
        organization_id: uuid.UUID,
        *,
        generation: int,
        records: list[ResealedRecord],
    ) -> int:
        return await self._repo.apply(organization_id, generation=generation, records=records)
