"""SQL implementation of the export repository port. See ADR-0006 §5.

Runs on a plain (non-tenant) ``db_session`` and re-binds the tenant GUC per organization, exactly as
account deletion does — an export spans every organization the user belongs to, and each query must
still run under RLS.

Sealed columns (``calendar_events.content``, ``tasks.content``, ``bookings.invitee_private``) are
read and passed through **verbatim**: the server cannot open them, and this is the one place where
that is a feature rather than a limitation.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.export import (
    AvailabilityOverrideExport,
    AvailabilityRuleExport,
    BookingExport,
    CaldavConnectionExport,
    CalendarEventExport,
    CalendarExport,
    EventTypeExport,
    ExportRepository,
    OrganizationExport,
    ProfileExport,
    ScheduleExport,
    SubscriptionExport,
    TaskExport,
)
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.membership import user_organizations
from ghostcal.infrastructure.db.session import bind_org


class SqlExportRepository(ExportRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def profile(self, user_id: uuid.UUID) -> ProfileExport | None:
        row = (
            await self._session.execute(
                select(
                    models.User.id,
                    models.User.email,
                    models.User.name,
                    models.User.timezone,
                    models.User.email_verified_at,
                    models.User.created_at,
                ).where(models.User.id == user_id)
            )
        ).first()
        if row is None:
            return None
        return ProfileExport(
            id=row.id,
            email=row.email,
            name=row.name,
            timezone=row.timezone,
            email_verified_at=row.email_verified_at,
            created_at=row.created_at,
        )

    async def organizations(self, user_id: uuid.UUID) -> list[OrganizationExport]:
        return [
            OrganizationExport(id=org_id, name=name, slug=slug, role=role)
            for org_id, name, slug, role in await user_organizations(self._session, user_id)
        ]

    async def calendars(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[CalendarExport]:
        await bind_org(self._session, organization_id)
        calendars = (
            await self._session.execute(
                select(models.Calendar)
                .where(models.Calendar.owner_id == user_id)
                .order_by(models.Calendar.created_at)
            )
        ).scalars()

        exported: list[CalendarExport] = []
        for calendar in calendars:
            events = (
                await self._session.execute(
                    select(models.CalendarEvent)
                    .where(models.CalendarEvent.calendar_id == calendar.id)
                    .order_by(models.CalendarEvent.start_at)
                )
            ).scalars()
            exported.append(
                CalendarExport(
                    id=calendar.id,
                    organization_id=organization_id,
                    name=calendar.name,
                    color=calendar.color,
                    is_default=calendar.is_default,
                    events=[
                        CalendarEventExport(
                            id=e.id,
                            calendar_id=e.calendar_id,
                            start_at=e.start_at,
                            end_at=e.end_at,
                            all_day=e.all_day,
                            timezone=e.timezone,
                            rrule=e.rrule,
                            exdates=list(e.exdates),
                            status=e.status,
                            reminder_minutes=e.reminder_minutes,
                            content_sealed=e.content,
                        )
                        for e in events
                    ],
                )
            )
        return exported

    async def tasks(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> list[TaskExport]:
        await bind_org(self._session, organization_id)
        rows = (
            await self._session.execute(
                select(models.Task)
                .where(models.Task.owner_id == user_id)
                .order_by(models.Task.created_at)
            )
        ).scalars()
        return [
            TaskExport(
                id=t.id,
                organization_id=organization_id,
                due_at=t.due_at,
                completed=t.completed,
                completed_at=t.completed_at,
                reminder_minutes=t.reminder_minutes,
                content_sealed=t.content,
            )
            for t in rows
        ]

    async def bookings(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> list[BookingExport]:
        await bind_org(self._session, organization_id)
        rows = (
            await self._session.execute(
                select(models.Booking, models.EventType.title)
                .join(models.EventType, models.EventType.id == models.Booking.event_type_id)
                .where(models.Booking.host_id == user_id)
                .order_by(models.Booking.start_at)
            )
        ).all()
        return [
            BookingExport(
                id=b.id,
                organization_id=organization_id,
                event_type_title=title,
                start_at=b.start_at,
                end_at=b.end_at,
                status=b.status,
                invitee_email=b.invitee_email,
                invitee_timezone=b.invitee_timezone,
                location=b.location,
                invitee_private_sealed=b.invitee_private,
            )
            for b, title in rows
        ]

    async def event_types(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[EventTypeExport]:
        await bind_org(self._session, organization_id)
        rows = (
            await self._session.execute(
                select(models.EventType)
                .where(models.EventType.owner_id == user_id)
                .order_by(models.EventType.created_at)
            )
        ).scalars()
        return [
            EventTypeExport(
                id=e.id,
                slug=e.slug,
                title=e.title,
                description=e.description,
                duration_min=e.duration_min,
                kind=e.kind,
                active=e.active,
            )
            for e in rows
        ]

    async def schedules(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[ScheduleExport]:
        await bind_org(self._session, organization_id)
        schedules = (
            await self._session.execute(
                select(models.AvailabilitySchedule)
                .where(models.AvailabilitySchedule.owner_id == user_id)
                .order_by(models.AvailabilitySchedule.created_at)
            )
        ).scalars()

        exported: list[ScheduleExport] = []
        for schedule in schedules:
            rules = (
                await self._session.execute(
                    select(models.AvailabilityRule)
                    .where(models.AvailabilityRule.schedule_id == schedule.id)
                    .order_by(models.AvailabilityRule.weekday, models.AvailabilityRule.start_time)
                )
            ).scalars()
            overrides = (
                await self._session.execute(
                    select(models.AvailabilityOverride)
                    .where(models.AvailabilityOverride.schedule_id == schedule.id)
                    .order_by(models.AvailabilityOverride.date)
                )
            ).scalars()
            exported.append(
                ScheduleExport(
                    id=schedule.id,
                    name=schedule.name,
                    timezone=schedule.timezone,
                    rules=[
                        AvailabilityRuleExport(
                            weekday=r.weekday, start_time=r.start_time, end_time=r.end_time
                        )
                        for r in rules
                    ],
                    overrides=[
                        AvailabilityOverrideExport(
                            date=o.date,
                            is_available=o.is_available,
                            start_time=o.start_time,
                            end_time=o.end_time,
                        )
                        for o in overrides
                    ],
                )
            )
        return exported

    async def subscriptions(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[SubscriptionExport]:
        await bind_org(self._session, organization_id)
        rows = (
            await self._session.execute(
                select(models.CalendarSubscription)
                .where(models.CalendarSubscription.owner_id == user_id)
                .order_by(models.CalendarSubscription.created_at)
            )
        ).scalars()
        return [
            SubscriptionExport(id=s.id, name=s.name, url=s.url, color=s.color, status=s.status)
            for s in rows
        ]

    async def caldav_connections(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[CaldavConnectionExport]:
        await bind_org(self._session, organization_id)
        # password_encrypted is pointedly not selected: an export must carry no credential.
        rows = (
            await self._session.execute(
                select(
                    models.CaldavConnection.id,
                    models.CaldavConnection.server_url,
                    models.CaldavConnection.username,
                    models.CaldavConnection.calendar_name,
                    models.CaldavConnection.status,
                ).where(models.CaldavConnection.user_id == user_id)
            )
        ).all()
        return [
            CaldavConnectionExport(
                id=r.id,
                server_url=r.server_url,
                username=r.username,
                calendar_name=r.calendar_name,
                status=r.status,
            )
            for r in rows
        ]
