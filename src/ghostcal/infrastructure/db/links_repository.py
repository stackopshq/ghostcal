"""SQL implementation of the public-calendar-link repository port (ADR-0009).

Everything the *owner* does runs under RLS in their org session, and is scoped to their own calendar
on top of that: RLS keeps other organizations out, and inside one, publishing a colleague's calendar
to the world is not a thing anyone should be able to do.

The *visitor* has no account and no organization, so they have no RLS context at all. They get one
door — ``public_calendar_by_token`` — and it hands back ciphertext.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.links import (
    LinkRecord,
    LinkRepository,
    PendingSeal,
    PublicCalendar,
    PublicEvent,
    SealedCopy,
)
from ghostcal.infrastructure.db import models


class SqlLinkRepository(LinkRepository):
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._org_id = organization_id

    async def _owns(self, owner_id: uuid.UUID, calendar_id: uuid.UUID) -> bool:
        return (
            await self._session.execute(
                select(models.Calendar.id).where(
                    models.Calendar.id == calendar_id,
                    models.Calendar.owner_id == owner_id,
                )
            )
        ).scalar_one_or_none() is not None

    async def create(
        self,
        owner_id: uuid.UUID,
        calendar_id: uuid.UUID,
        *,
        token_hash: str,
        public_key: str,
        name: str,
    ) -> uuid.UUID | None:
        if not await self._owns(owner_id, calendar_id):
            return None
        return (
            await self._session.execute(
                pg_insert(models.CalendarLink)
                .values(
                    organization_id=self._org_id,
                    calendar_id=calendar_id,
                    token_hash=token_hash,
                    public_key=public_key,
                    name=name,
                )
                .returning(models.CalendarLink.id)
            )
        ).scalar_one()

    async def list_for_calendar(
        self, owner_id: uuid.UUID, calendar_id: uuid.UUID
    ) -> list[LinkRecord]:
        if not await self._owns(owner_id, calendar_id):
            return []

        # How many of the calendar's events this link still has no sealed copy of. That number is
        # what the owner's browser has left to do, and it is worth showing: a link whose copies are
        # not made yet shows an empty calendar, which looks like a bug rather than a pending job.
        events = (
            select(func.count())
            .select_from(models.CalendarEvent)
            .where(models.CalendarEvent.calendar_id == calendar_id)
            .scalar_subquery()
        )
        copies = (
            select(func.count())
            .select_from(models.CalendarLinkEvent)
            .where(models.CalendarLinkEvent.link_id == models.CalendarLink.id)
            .scalar_subquery()
        )
        rows = (
            await self._session.execute(
                select(
                    models.CalendarLink.id,
                    models.CalendarLink.calendar_id,
                    models.CalendarLink.name,
                    models.CalendarLink.public_key,
                    models.CalendarLink.created_at,
                    (events - copies).label("pending"),
                )
                .where(models.CalendarLink.calendar_id == calendar_id)
                .order_by(models.CalendarLink.created_at)
            )
        ).all()
        return [
            LinkRecord(
                id=r.id,
                calendar_id=r.calendar_id,
                name=r.name,
                public_key=r.public_key,
                created_at=r.created_at,
                pending=max(0, r.pending),
            )
            for r in rows
        ]

    async def delete(self, owner_id: uuid.UUID, link_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(models.CalendarLink)
            .where(
                models.CalendarLink.id == link_id,
                models.CalendarLink.calendar_id.in_(
                    select(models.Calendar.id).where(models.Calendar.owner_id == owner_id)
                ),
            )
            .returning(models.CalendarLink.id)
        )
        return result.scalar_one_or_none() is not None

    async def pending_seals(
        self, owner_id: uuid.UUID, link_id: uuid.UUID, *, limit: int
    ) -> list[PendingSeal]:
        copied = (
            select(models.CalendarLinkEvent.event_id)
            .where(models.CalendarLinkEvent.link_id == link_id)
            .scalar_subquery()
        )
        rows = (
            await self._session.execute(
                select(models.CalendarEvent.id, models.CalendarEvent.content)
                .join(models.Calendar, models.Calendar.id == models.CalendarEvent.calendar_id)
                .join(models.CalendarLink, models.CalendarLink.calendar_id == models.Calendar.id)
                .where(
                    models.CalendarLink.id == link_id,
                    models.Calendar.owner_id == owner_id,
                    models.CalendarEvent.id.not_in(copied),
                )
                .order_by(models.CalendarEvent.start_at)
                .limit(limit)
            )
        ).all()
        return [PendingSeal(event_id=r.id, content=r.content) for r in rows]

    async def store_copies(
        self, owner_id: uuid.UUID, link_id: uuid.UUID, copies: list[SealedCopy]
    ) -> int:
        link = (
            await self._session.execute(
                select(models.CalendarLink.id)
                .join(models.Calendar, models.Calendar.id == models.CalendarLink.calendar_id)
                .where(
                    models.CalendarLink.id == link_id,
                    models.Calendar.owner_id == owner_id,
                )
            )
        ).scalar_one_or_none()
        if link is None:
            return 0

        for copy in copies:
            await self._session.execute(
                pg_insert(models.CalendarLinkEvent)
                .values(
                    link_id=link_id,
                    event_id=copy.event_id,
                    organization_id=self._org_id,
                    content_sealed=copy.content_sealed,
                )
                .on_conflict_do_update(
                    index_elements=["link_id", "event_id"],
                    set_={"content_sealed": copy.content_sealed},
                )
            )
        return len(copies)

    async def public_calendar(self, token_hash: str) -> PublicCalendar | None:
        rows = (
            await self._session.execute(
                text(
                    "SELECT calendar_name, owner_name, start_at, end_at, all_day, timezone, "
                    "rrule, exdates, content_sealed FROM public_calendar_by_token(:h)"
                ),
                {"h": token_hash},
            )
        ).all()
        if not rows:
            return None

        return PublicCalendar(
            calendar_name=rows[0].calendar_name,
            owner_name=rows[0].owner_name,
            events=[
                PublicEvent(
                    start_at=r.start_at,
                    end_at=r.end_at,
                    all_day=r.all_day,
                    timezone=r.timezone,
                    rrule=r.rrule,
                    exdates=list(r.exdates or []),
                    content_sealed=r.content_sealed,
                )
                # A link with no copies yet joins to one all-NULL row. That is an empty calendar,
                # not an event.
                for r in rows
                if r.content_sealed is not None
            ],
        )
