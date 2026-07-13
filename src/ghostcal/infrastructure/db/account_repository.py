"""SQL implementation of the account lifecycle repository port. See ADR-0006.

Runs on a plain (non-tenant) ``db_session``: erasure spans every organization the user belongs to,
so it re-binds the tenant GUC per organization as it goes. Which organizations those are is read
through the existing ``user_organizations`` SECURITY DEFINER function — ``memberships`` is itself
RLS-scoped, so a cross-tenant read is impossible under the plain policy.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.account import (
    AccountRepository,
    CancelledBooking,
    OrgStanding,
)
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.membership import user_organizations
from ghostcal.infrastructure.db.session import bind_org


class SqlAccountRepository(AccountRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def org_standings(self, user_id: uuid.UUID) -> list[OrgStanding]:
        standings: list[OrgStanding] = []
        for organization_id, _name, _slug, role in await user_organizations(self._session, user_id):
            # Under the org's GUC, RLS scopes the count to that organization on its own.
            await bind_org(self._session, organization_id)
            row = (
                await self._session.execute(
                    select(
                        func.count().label("members"),
                        func.count().filter(models.Membership.role == "owner").label("owners"),
                    ).select_from(models.Membership)
                )
            ).one()
            standings.append(
                OrgStanding(
                    organization_id=organization_id,
                    role=role,
                    member_count=row.members,
                    owner_count=row.owners,
                )
            )
        return standings

    async def delete_organization(self, organization_id: uuid.UUID) -> None:
        await bind_org(self._session, organization_id)
        # Order matters. ``bookings.event_type_id`` is ON DELETE RESTRICT, and PostgreSQL enforces
        # RESTRICT immediately — it does not wait to see that the referencing bookings are about to
        # be cascade-deleted by the same statement. So bookings go first, then event types, and only
        # then the organization, whose CASCADE sweeps up everything else.
        await self._session.execute(
            delete(models.Booking).where(models.Booking.organization_id == organization_id)
        )
        await self._session.execute(
            delete(models.EventType).where(models.EventType.organization_id == organization_id)
        )
        await self._session.execute(
            delete(models.Organization).where(models.Organization.id == organization_id)
        )

    async def anonymize_in_org(
        self, organization_id: uuid.UUID, user_id: uuid.UUID, *, now: datetime
    ) -> list[CancelledBooking]:
        await bind_org(self._session, organization_id)

        # Read the future bookings before touching them: the invitee has to be told the meeting is
        # off, and the title lives on the event type. ``invitee_email`` decrypts through its
        # TypeDecorator on the way out.
        rows = (
            await self._session.execute(
                select(
                    models.Booking.invitee_email,
                    models.Booking.invitee_timezone,
                    models.Booking.start_at,
                    models.EventType.title,
                )
                .join(models.EventType, models.EventType.id == models.Booking.event_type_id)
                .where(
                    models.Booking.host_id == user_id,
                    models.Booking.status == "confirmed",
                    models.Booking.start_at > now,
                )
            )
        ).all()
        cancelled = [
            CancelledBooking(
                invitee_email=r.invitee_email,
                invitee_timezone=r.invitee_timezone,
                event_title=r.title,
                start_at=r.start_at,
            )
            for r in rows
        ]

        # Take the rows out of the ``no_overlap_per_host`` exclusion constraint BEFORE reassigning
        # them. The constraint is EXCLUDE (host_id =, period &&) WHERE (status = 'confirmed' AND
        # blocks_host): funnelling several deleted hosts' overlapping meetings onto the single
        # tombstone host would collide. Cancelling the future ones and clearing blocks_host on
        # all of them empties that WHERE clause, so the reassignment below can never fire it.
        # (ADR-0006 §3.)
        await self._session.execute(
            update(models.Booking)
            .where(
                models.Booking.host_id == user_id,
                models.Booking.status == "confirmed",
                models.Booking.start_at > now,
            )
            .values(status="cancelled")
        )
        await self._session.execute(
            update(models.Booking)
            .where(models.Booking.host_id == user_id)
            .values(blocks_host=False)
        )
        await self._session.execute(
            update(models.Booking)
            .where(models.Booking.host_id == user_id)
            .values(host_id=models.TOMBSTONE_USER_ID)
        )

        # Event types cannot be deleted (historical bookings reference them with RESTRICT), so they
        # are deactivated instead: the booking page stops taking bookings — there is no host behind
        # it any more — while the row survives to keep those bookings referentially intact.
        await self._session.execute(
            update(models.EventType)
            .where(models.EventType.owner_id == user_id)
            .values(owner_id=models.TOMBSTONE_USER_ID, active=False)
        )
        return cancelled

    async def delete_user(self, user_id: uuid.UUID) -> None:
        # ``users`` is not RLS-scoped. Everything strictly personal (credentials, identities,
        # tokens, memberships, wrapped org keys, calendars and their events, tasks, schedules,
        # CalDAV connections, subscriptions, polls) cascades from this row.
        await self._session.execute(delete(models.User).where(models.User.id == user_id))
