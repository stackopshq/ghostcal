"""Account lifecycle use cases: erasure (GDPR art. 17). See ADR-0006.

Deleting an account erases the natural person without destroying an organization's history:

- an organization the user is the **sole member** of is deleted outright (everything cascades);
- in a **shared** organization the user is anonymized out of the records that are co-owned with it
  (bookings, event types), while everything strictly personal cascades away with the ``users`` row.

Deletion is refused when the user is the sole *owner* of a shared organization: an organization must
stay administrable, so another owner has to be promoted first.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from ghostcal.application.auth import AuthRepository
from ghostcal.application.ports.security import PasswordHasher


class AccountError(Exception):
    """Base class for account lifecycle errors."""


class UnknownUser(AccountError):
    pass


class ConfirmationMismatch(AccountError):
    """The typed confirmation does not match the account's email address."""


class InvalidPassword(AccountError):
    pass


class SoleOwner(AccountError):
    """The user is the last owner of an organization that has other members."""

    def __init__(self, organization_id: uuid.UUID) -> None:
        super().__init__(f"sole owner of organization {organization_id}")
        self.organization_id = organization_id


@dataclass(frozen=True)
class OrgStanding:
    """The user's position in one organization, as far as deletion is concerned."""

    organization_id: uuid.UUID
    role: str
    member_count: int
    owner_count: int

    @property
    def is_sole_member(self) -> bool:
        return self.member_count == 1


@dataclass(frozen=True)
class CancelledBooking:
    """A future booking cancelled because its host is being deleted — its invitee must be told."""

    invitee_email: str
    invitee_timezone: str
    event_title: str
    start_at: datetime


class AccountRepository:
    async def org_standings(self, user_id: uuid.UUID) -> list[OrgStanding]:
        """The user's standing in every organization they belong to."""
        raise NotImplementedError

    async def delete_organization(self, organization_id: uuid.UUID) -> None:
        """Delete an organization and everything that cascades from it."""
        raise NotImplementedError

    async def anonymize_in_org(
        self, organization_id: uuid.UUID, user_id: uuid.UUID, *, now: datetime
    ) -> list[CancelledBooking]:
        """Reassign the user's org-owned records to the tombstone user.

        Cancels the user's future confirmed bookings (the host is going away, so the meeting will
        not happen) and returns them so their invitees can be notified once the transaction commits.
        """
        raise NotImplementedError

    async def delete_user(self, user_id: uuid.UUID) -> None:
        """Delete the ``users`` row. Everything strictly personal cascades from it."""
        raise NotImplementedError


class AccountService:
    def __init__(
        self, repo: AccountRepository, auth_repo: AuthRepository, hasher: PasswordHasher
    ) -> None:
        self._repo = repo
        self._auth = auth_repo
        self._hasher = hasher

    async def delete(
        self,
        user_id: uuid.UUID,
        *,
        email_confirmation: str,
        password: str | None,
        now: datetime,
    ) -> list[CancelledBooking]:
        """Erase the account. Returns the bookings whose invitees must be notified.

        The caller sends those emails *after* the transaction commits: a failing SMTP server must
        not roll the erasure back.
        """
        user = await self._auth.get_by_id(user_id)
        if user is None:
            raise UnknownUser("unknown user")

        # Always require the address typed back — it is the only confirmation an SSO-only account
        # (which has no password) can give, and it makes the destructive step deliberate for both.
        if email_confirmation.strip().casefold() != user.email.casefold():
            raise ConfirmationMismatch("the typed address does not match this account")
        if user.password_hash is not None and (
            password is None or not self._hasher.verify(user.password_hash, password)
        ):
            raise InvalidPassword("password is incorrect")

        standings = await self._repo.org_standings(user_id)

        # Check every organization before touching any of them, so a refusal leaves nothing behind.
        for standing in standings:
            if (
                not standing.is_sole_member
                and standing.role == "owner"
                and standing.owner_count == 1
            ):
                raise SoleOwner(standing.organization_id)

        cancelled: list[CancelledBooking] = []
        for standing in standings:
            if standing.is_sole_member:
                await self._repo.delete_organization(standing.organization_id)
            else:
                cancelled += await self._repo.anonymize_in_org(
                    standing.organization_id, user_id, now=now
                )

        await self._repo.delete_user(user_id)
        return cancelled
