"""SQL implementation of the calendar repository (org-scoped session, RLS applies)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, insert, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.calendar import (
    BusyBlock,
    CalendarRecord,
    CalendarRepository,
    DefaultCalendarUndeletable,
    EventInput,
    EventRecord,
    ShareRecord,
    SubEvent,
)
from ghostcal.infrastructure.db import models


class SqlCalendarRepository(CalendarRepository):
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._org_id = organization_id

    async def list_calendars(self, owner_id: uuid.UUID) -> list[CalendarRecord]:
        owned = (
            (
                await self._session.execute(
                    select(models.Calendar)
                    .where(models.Calendar.owner_id == owner_id)
                    .order_by(models.Calendar.created_at)
                )
            )
            .scalars()
            .all()
        )
        shared = (
            await self._session.execute(
                select(models.Calendar, models.User.name, models.CalendarShare.can_edit)
                .join(models.CalendarShare, models.CalendarShare.calendar_id == models.Calendar.id)
                .join(models.User, models.User.id == models.Calendar.owner_id)
                .where(models.CalendarShare.shared_with_user_id == owner_id)
                .order_by(models.Calendar.created_at)
            )
        ).all()
        return [_calendar(c) for c in owned] + [
            _calendar(c, is_shared=True, owner_name=name, can_edit=can_edit)
            for c, name, can_edit in shared
        ]

    async def share_calendar(
        self, owner_id: uuid.UUID, calendar_id: uuid.UUID, user_id: uuid.UUID, *, can_edit: bool
    ) -> bool:
        if not await self._owns(owner_id, calendar_id):
            return False
        # Upsert rather than do-nothing: re-sharing is how the owner changes read-only to read-write
        # and back. A silent no-op would leave the owner believing they had granted edit.
        await self._session.execute(
            pg_insert(models.CalendarShare)
            .values(
                organization_id=self._org_id,
                calendar_id=calendar_id,
                shared_with_user_id=user_id,
                can_edit=can_edit,
            )
            .on_conflict_do_update(
                index_elements=["calendar_id", "shared_with_user_id"],
                set_={"can_edit": can_edit},
            )
        )
        return True

    # Access is a property of the CALENDAR, not of who happens to have created an event on it. That
    # is the only rule that stays coherent once a shared calendar can be written to: an event an
    # editor adds to someone else's calendar has to be visible to its owner, and an owner-keyed rule
    # would hide it from them.

    def _writable_calendar_ids(self, user_id: uuid.UUID) -> Any:
        """Calendars the user may write to: their own, plus those shared with them *for editing*."""
        own = select(models.Calendar.id).where(models.Calendar.owner_id == user_id)
        shared = select(models.CalendarShare.calendar_id).where(
            models.CalendarShare.shared_with_user_id == user_id,
            models.CalendarShare.can_edit.is_(True),
        )
        return own.union(shared).subquery().select()

    def _readable_calendar_ids(self, user_id: uuid.UUID) -> Any:
        """Calendars the user may see: their own, plus every calendar shared with them."""
        own = select(models.Calendar.id).where(models.Calendar.owner_id == user_id)
        shared = select(models.CalendarShare.calendar_id).where(
            models.CalendarShare.shared_with_user_id == user_id
        )
        return own.union(shared).subquery().select()

    async def can_write(self, user_id: uuid.UUID, calendar_id: uuid.UUID) -> bool:
        return (
            await self._session.execute(
                select(models.Calendar.id).where(
                    models.Calendar.id == calendar_id,
                    models.Calendar.id.in_(self._writable_calendar_ids(user_id)),
                )
            )
        ).scalar_one_or_none() is not None

    async def unshare_calendar(
        self, owner_id: uuid.UUID, calendar_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        if not await self._owns(owner_id, calendar_id):
            return False
        await self._session.execute(
            delete(models.CalendarShare).where(
                models.CalendarShare.calendar_id == calendar_id,
                models.CalendarShare.shared_with_user_id == user_id,
            )
        )
        return True

    async def list_shares(self, owner_id: uuid.UUID, calendar_id: uuid.UUID) -> list[ShareRecord]:
        if not await self._owns(owner_id, calendar_id):
            return []
        rows = (
            await self._session.execute(
                select(models.User.id, models.User.name, models.CalendarShare.can_edit)
                .join(
                    models.CalendarShare, models.CalendarShare.shared_with_user_id == models.User.id
                )
                .where(models.CalendarShare.calendar_id == calendar_id)
                .order_by(models.User.name)
            )
        ).all()
        return [ShareRecord(user_id=r.id, name=r.name, can_edit=r.can_edit) for r in rows]

    async def _owns(self, owner_id: uuid.UUID, calendar_id: uuid.UUID) -> bool:
        return (
            await self._session.execute(
                select(models.Calendar.id).where(
                    models.Calendar.id == calendar_id, models.Calendar.owner_id == owner_id
                )
            )
        ).scalar_one_or_none() is not None

    async def ensure_default_calendar(self, owner_id: uuid.UUID, *, name: str) -> CalendarRecord:
        existing = (
            await self._session.execute(
                select(models.Calendar)
                .where(
                    models.Calendar.owner_id == owner_id,
                    models.Calendar.is_default.is_(True),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return _calendar(existing)
        row = (
            await self._session.execute(
                insert(models.Calendar)
                .values(
                    organization_id=self._org_id,
                    owner_id=owner_id,
                    # The name comes from the caller, in the language of the request that
                    # creates this calendar (see `list_calendars`). A fixed string here swung
                    # once from "My calendar" to « Mon agenda » and was wrong for half the
                    # users either way. It is only a starting point: PATCH
                    # /v1/me/calendars/{id} renames it, and existing calendars never get here.
                    name=name,
                    color="#00f0ff",
                    is_default=True,
                )
                .returning(models.Calendar)
            )
        ).scalar_one()
        return _calendar(row)

    async def create_calendar(
        self, owner_id: uuid.UUID, *, name: str, color: str
    ) -> CalendarRecord:
        row = (
            await self._session.execute(
                insert(models.Calendar)
                .values(organization_id=self._org_id, owner_id=owner_id, name=name, color=color)
                .returning(models.Calendar)
            )
        ).scalar_one()
        return _calendar(row)

    async def update_calendar(
        self,
        owner_id: uuid.UUID,
        calendar_id: uuid.UUID,
        *,
        name: str | None = None,
        color: str | None = None,
    ) -> bool:
        # `owner_id` in the WHERE clause, not in a prior SELECT: it is what stops one member
        # renaming or recolouring another's calendar, and it has to be part of the same statement
        # to do so. A shared calendar is deliberately not covered — the viewer sees the owner's
        # name and colour.
        values: dict[str, str] = {}
        if name is not None:
            values["name"] = name
        if color is not None:
            values["color"] = color
        if not values:
            raise ValueError("nothing to update")
        row = (
            await self._session.execute(
                update(models.Calendar)
                .where(
                    models.Calendar.id == calendar_id,
                    models.Calendar.owner_id == owner_id,
                    models.Calendar.organization_id == self._org_id,
                )
                .values(**values)
                .returning(models.Calendar.id)
            )
        ).scalar_one_or_none()
        return row is not None

    async def delete_calendar(self, owner_id: uuid.UUID, calendar_id: uuid.UUID) -> bool:
        # Deux instructions, et l'ordre compte. On lit d'abord `is_default` pour pouvoir refuser
        # *en le disant* : une suppression qui écarterait le calendrier par défaut dans sa clause
        # WHERE rendrait « introuvable », et l'utilisateur chercherait un calendrier qu'il a sous
        # les yeux. Les deux issues ne sont pas la même phrase.
        #
        # L'`owner_id` et l'`organization_id` restent néanmoins dans la clause WHERE de la
        # suppression, et pas seulement dans ce SELECT : une vérification suivie d'une écriture
        # laisse une fenêtre entre les deux, et c'est ce que les autres méthodes de ce dépôt
        # évitent déjà.
        defaut = (
            await self._session.execute(
                select(models.Calendar.is_default).where(
                    models.Calendar.id == calendar_id,
                    models.Calendar.owner_id == owner_id,
                    models.Calendar.organization_id == self._org_id,
                )
            )
        ).scalar_one_or_none()
        if defaut is None:
            return False
        if defaut:
            raise DefaultCalendarUndeletable(str(calendar_id))

        # Les événements, les partages, les liens de réservation et les rappels s'en vont avec la
        # ligne : toutes les clés étrangères qui pointent vers `calendars.id` sont en
        # `ON DELETE CASCADE`. Les effacer ici ferait plusieurs instructions là où la base en fait
        # une, et une coupure au milieu laisserait un calendrier sans ses événements.
        row = (
            await self._session.execute(
                delete(models.Calendar)
                .where(
                    models.Calendar.id == calendar_id,
                    models.Calendar.owner_id == owner_id,
                    models.Calendar.organization_id == self._org_id,
                )
                .returning(models.Calendar.id)
            )
        ).scalar_one_or_none()
        return row is not None

    async def get_event(self, owner_id: uuid.UUID, event_id: uuid.UUID) -> EventRecord | None:
        row = (
            await self._session.execute(
                select(models.CalendarEvent).where(
                    models.CalendarEvent.id == event_id,
                    models.CalendarEvent.calendar_id.in_(self._readable_calendar_ids(owner_id)),
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        writable = await self.can_write(owner_id, row.calendar_id)
        return _event(row, read_only=not writable)

    async def create_event(self, owner_id: uuid.UUID, data: EventInput) -> uuid.UUID:
        return (
            await self._session.execute(
                insert(models.CalendarEvent)
                .values(organization_id=self._org_id, owner_id=owner_id, **_event_values(data))
                .returning(models.CalendarEvent.id)
            )
        ).scalar_one()

    async def update_event(
        self, owner_id: uuid.UUID, event_id: uuid.UUID, data: EventInput
    ) -> bool:
        result = await self._session.execute(
            update(models.CalendarEvent)
            .where(
                models.CalendarEvent.id == event_id,
                # The event's *current* calendar must be writable too, or an editor could move an
                # event off a calendar they may write to and onto one they may not.
                models.CalendarEvent.calendar_id.in_(self._writable_calendar_ids(owner_id)),
            )
            .values(**_event_values(data))
            .returning(models.CalendarEvent.id)
        )
        return result.first() is not None

    async def delete_event(self, owner_id: uuid.UUID, event_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(models.CalendarEvent)
            .where(
                models.CalendarEvent.id == event_id,
                models.CalendarEvent.calendar_id.in_(self._writable_calendar_ids(owner_id)),
            )
            .returning(models.CalendarEvent.id)
        )
        return result.first() is not None

    async def events_overlapping(
        self, owner_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[EventRecord]:
        # Every event on a calendar the viewer may see — theirs, and those shared with them. Which
        # of them are editable is a property of the calendar, not of who created the event: an event
        # an editor added to someone else's calendar belongs to that calendar, and its owner must
        # see it.
        writable = set(
            (
                await self._session.execute(
                    select(models.Calendar.id).where(
                        models.Calendar.id.in_(self._writable_calendar_ids(owner_id))
                    )
                )
            )
            .scalars()
            .all()
        )
        rows = (
            (
                await self._session.execute(
                    select(models.CalendarEvent).where(
                        models.CalendarEvent.start_at < end,
                        or_(
                            models.CalendarEvent.rrule.is_not(None),
                            models.CalendarEvent.end_at > start,
                        ),
                        models.CalendarEvent.calendar_id.in_(self._readable_calendar_ids(owner_id)),
                    )
                )
            )
            .scalars()
            .all()
        )
        return [_event(r, read_only=r.calendar_id not in writable) for r in rows]

    async def bookings_in_range(
        self, owner_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[BusyBlock]:
        rows = (
            await self._session.execute(
                select(
                    models.Booking.start_at,
                    models.Booking.end_at,
                    models.EventType.title,
                    # Qui a réservé. Sans ces deux colonnes, l'agenda ne nommait que le type
                    # de rendez-vous — « RDV en visioconférence » — et il fallait ouvrir la
                    # fiche pour savoir de qui il s'agissait.
                    models.Booking.invitee_name,
                    models.Booking.invitee_private,
                )
                .join(models.EventType, models.Booking.event_type_id == models.EventType.id)
                .where(
                    models.Booking.host_id == owner_id,
                    models.Booking.status == "confirmed",
                    models.Booking.start_at < end,
                    models.Booking.end_at > start,
                )
            )
        ).all()
        return [
            BusyBlock(
                start_at=r.start_at,
                end_at=r.end_at,
                title=r.title,
                invitee_name=r.invitee_name,
                invitee_private=r.invitee_private,
            )
            for r in rows
        ]

    async def external_busy_in_range(
        self, owner_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[BusyBlock]:
        rows = (
            await self._session.execute(
                select(
                    models.ExternalBusy.start_at,
                    models.ExternalBusy.end_at,
                    models.ExternalBusy.summary,
                    models.ExternalBusy.connection_id,
                ).where(
                    models.ExternalBusy.host_id == owner_id,
                    models.ExternalBusy.start_at < end,
                    models.ExternalBusy.end_at > start,
                )
            )
        ).all()
        return [
            BusyBlock(
                start_at=r.start_at,
                end_at=r.end_at,
                title=r.summary,
                connection_id=r.connection_id,
            )
            for r in rows
        ]

    async def subscription_events_in_range(
        self, owner_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[SubEvent]:
        rows = (
            await self._session.execute(
                select(
                    models.SubscriptionEvent.subscription_id,
                    models.SubscriptionEvent.start_at,
                    models.SubscriptionEvent.end_at,
                    models.SubscriptionEvent.all_day,
                    models.SubscriptionEvent.summary,
                    models.SubscriptionEvent.location,
                    models.SubscriptionEvent.description,
                ).where(
                    models.SubscriptionEvent.owner_id == owner_id,
                    models.SubscriptionEvent.start_at < end,
                    models.SubscriptionEvent.end_at > start,
                )
            )
        ).all()
        return [
            SubEvent(
                subscription_id=r.subscription_id,
                start_at=r.start_at,
                end_at=r.end_at,
                all_day=r.all_day,
                summary=r.summary,
                location=r.location,
                description=r.description,
            )
            for r in rows
        ]


def _calendar(
    row: models.Calendar,
    *,
    is_shared: bool = False,
    owner_name: str | None = None,
    can_edit: bool = False,
) -> CalendarRecord:
    return CalendarRecord(
        id=row.id,
        name=row.name,
        color=row.color,
        is_default=row.is_default,
        is_shared=is_shared,
        owner_name=owner_name,
        # A calendar you own is always writable; can_edit only means anything for a shared one.
        can_edit=can_edit or not is_shared,
    )


def _event(row: models.CalendarEvent, *, read_only: bool = False) -> EventRecord:
    return EventRecord(
        id=row.id,
        calendar_id=row.calendar_id,
        start_at=row.start_at,
        end_at=row.end_at,
        timezone=row.timezone,
        all_day=row.all_day,
        rrule=row.rrule,
        exdates=tuple(row.exdates),
        content=row.content,
        reminder_minutes=row.reminder_minutes,
        read_only=read_only,
    )


def _event_values(data: EventInput) -> dict[str, object]:
    return {
        "calendar_id": data.calendar_id,
        "start_at": data.start_at,
        "end_at": data.end_at,
        "timezone": data.timezone,
        "all_day": data.all_day,
        "rrule": data.rrule,
        "exdates": list(data.exdates),
        "status": "confirmed",
        "content": data.content,
        "reminder_minutes": data.reminder_minutes,
    }
