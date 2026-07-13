"""Org key rotation use cases (ADR-0007) — what finally makes removing a member *revoke* something.

The whole operation happens in the rotating admin's browser: it holds the current org private key,
so it is the only place a new keypair can be minted and handed to the other members. It generates
the new pair, seals the new private key to each member's public key, and posts the result here.

The server cannot check any of that crypto, and does not pretend to. What it *can* check — and what
this module is — is that the rotation is **complete and closed**:

- every current member is provided for. Rotating past someone locks them out of their own
  organization's data, silently, and only they would find out;
- and nobody else is slipped in. A key for a non-member is a key for an outsider.

The flip itself is one transaction: the new per-member keys are inserted and the organization's
public key is advanced together, or neither happens.

What is deliberately *not* here: re-sealing the existing records. Advancing the public key protects
everything created from that moment on, which is the urgent half and the only half that has to be
atomic. The backlog is already readable by whoever left; re-sealing it narrows what they can still
read later, and can take as long as it takes. See ADR-0007 §2.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


class RotationError(Exception):
    """Base class for rotation errors."""


class NotAuthorized(RotationError):
    """Only an owner or an admin may rotate an organization's key."""


class MembersLeftBehind(RotationError):
    """Some members got no new key. Naming them is the point — a silent lockout is the failure."""

    def __init__(self, emails: list[str]) -> None:
        super().__init__("no new key provided for: " + ", ".join(emails))
        self.emails = emails


class MembersWithoutKeypair(RotationError):
    """Some members have no public key to seal to: they have not logged in since ADR-0007."""

    def __init__(self, emails: list[str]) -> None:
        super().__init__(
            "these members have no encryption key yet — they must log in once first: "
            + ", ".join(emails)
        )
        self.emails = emails


class NotAMember(RotationError):
    """A key was offered for someone outside the organization."""


@dataclass(frozen=True)
class SealedMemberKey:
    """The new org private key, sealed to one member's public key. Opaque to the server."""

    user_id: uuid.UUID
    sealed_org_key: str


class RotationRepository:
    async def members_without_keypair(self, organization_id: uuid.UUID) -> list[str]:
        """Emails of members with no public key — a rotation cannot provide for them."""
        raise NotImplementedError

    async def rotate(
        self,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID,
        *,
        public_key: str,
        member_keys: list[SealedMemberKey],
    ) -> int:
        """Advance the org to a new keypair. Returns the new generation."""
        raise NotImplementedError


class RotationService:
    def __init__(self, repo: RotationRepository) -> None:
        self._repo = repo

    async def rotate(
        self,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID,
        *,
        public_key: str,
        member_keys: list[SealedMemberKey],
    ) -> int:
        # Checked before the flip so the refusal is a clean no-op, and checked here rather than only
        # in the database so the caller is told *who* is missing and what to do about it.
        stragglers = await self._repo.members_without_keypair(organization_id)
        if stragglers:
            raise MembersWithoutKeypair(stragglers)

        return await self._repo.rotate(
            organization_id, actor_id, public_key=public_key, member_keys=member_keys
        )
