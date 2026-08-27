"""Booking retention use cases: storage limitation (GDPR art. 5.1.e). See ADR-0006.

An organization may set a retention window; bookings that ended longer ago than that are purged by a
periodic job. The window is **opt-in** — NULL means keep forever, which is what every organization
starts with, so nothing is destroyed until someone deliberately asks for it.

The purge is the only irreversible periodic job in the system. Two guards, deliberately redundant:
the window is floored here *and* by a check constraint in the database, and the job reports what it
destroyed per organization so a purge is never silent.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

# Mirrors the ck_organizations_booking_retention_floor check constraint (migration c9e4a71b6d38).
# Bookings are the organization's operational record; a window under a month is far more likely to
# be a mistake than a policy.
MIN_RETENTION_DAYS = 30
MAX_RETENTION_DAYS = 3650  # 10 years — beyond this, "keep forever" is what is actually meant.


class RetentionError(Exception):
    """Base class for retention errors."""


class InvalidRetentionWindow(RetentionError):
    pass


@dataclass(frozen=True)
class PurgeResult:
    organization_id: uuid.UUID
    purged: int


class RetentionRepository:
    async def set_window(self, organization_id: uuid.UUID, days: int | None) -> None:
        """Set (or clear, with None) the organization's retention window."""
        raise NotImplementedError

    async def get_window(self, organization_id: uuid.UUID) -> int | None:
        raise NotImplementedError

    async def purge_expired(self) -> list[PurgeResult]:
        """Purge expired bookings across every organization that has a window set."""
        raise NotImplementedError


def validate_window(days: int | None) -> int | None:
    if days is None:
        return None
    if days < MIN_RETENTION_DAYS:
        raise InvalidRetentionWindow(
            f"a retention window must be at least {MIN_RETENTION_DAYS} days"
        )
    if days > MAX_RETENTION_DAYS:
        raise InvalidRetentionWindow(
            f"a retention window must be at most {MAX_RETENTION_DAYS} days; "
            "leave it unset to keep bookings forever"
        )
    return days


class RetentionService:
    def __init__(self, repo: RetentionRepository) -> None:
        self._repo = repo

    async def get(self, organization_id: uuid.UUID) -> int | None:
        return await self._repo.get_window(organization_id)

    async def set(self, organization_id: uuid.UUID, days: int | None) -> int | None:
        window = validate_window(days)
        await self._repo.set_window(organization_id, window)
        return window


async def purge_expired_bookings(repo: RetentionRepository) -> list[PurgeResult]:
    """Run the purge. Returns what was destroyed, per organization, so the caller can log it."""
    return await repo.purge_expired()
