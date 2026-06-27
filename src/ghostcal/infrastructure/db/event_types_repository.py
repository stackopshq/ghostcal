"""SQL implementation of the event-types repository port (org-scoped, owner-filtered)."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.event_types import (
    EventTypeData,
    EventTypeInput,
    EventTypeInUse,
    EventTypesRepository,
)
from ghostcal.infrastructure.db import models


class SqlEventTypesRepository(EventTypesRepository):
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._org_id = organization_id

    async def list_for_owner(self, owner_id: uuid.UUID) -> list[EventTypeData]:
        rows = (
            (
                await self._session.execute(
                    select(models.EventType)
                    .where(models.EventType.owner_id == owner_id)
                    .order_by(models.EventType.created_at)
                )
            )
            .scalars()
            .all()
        )
        org_slug = await self._org_slug()
        return [_to_data(r, org_slug) for r in rows]

    async def get(self, event_type_id: uuid.UUID, owner_id: uuid.UUID) -> EventTypeData | None:
        row = (
            await self._session.execute(
                select(models.EventType).where(
                    models.EventType.id == event_type_id,
                    models.EventType.owner_id == owner_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return _to_data(row, await self._org_slug())

    async def _org_slug(self) -> str:
        return (
            await self._session.execute(
                select(models.Organization.slug).where(models.Organization.id == self._org_id)
            )
        ).scalar_one()

    async def create(self, owner_id: uuid.UUID, slug: str, data: EventTypeInput) -> uuid.UUID:
        return (
            await self._session.execute(
                insert(models.EventType)
                .values(
                    organization_id=self._org_id,
                    owner_id=owner_id,
                    schedule_id=None,  # falls back to the owner's schedule for now
                    slug=slug,
                    **_values(data),
                )
                .returning(models.EventType.id)
            )
        ).scalar_one()

    async def update(
        self, event_type_id: uuid.UUID, owner_id: uuid.UUID, data: EventTypeInput
    ) -> bool:
        row = await self._owned(event_type_id, owner_id)
        if row is None:
            return False
        for field, value in _values(data).items():
            setattr(row, field, value)
        return True

    async def delete(self, event_type_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
        try:
            deleted = (
                await self._session.execute(
                    delete(models.EventType)
                    .where(
                        models.EventType.id == event_type_id,
                        models.EventType.owner_id == owner_id,
                    )
                    .returning(models.EventType.id)
                )
            ).scalar_one_or_none()
        except IntegrityError as exc:
            raise EventTypeInUse(str(event_type_id)) from exc
        return deleted is not None

    async def _owned(
        self, event_type_id: uuid.UUID, owner_id: uuid.UUID
    ) -> models.EventType | None:
        return (
            await self._session.execute(
                select(models.EventType).where(
                    models.EventType.id == event_type_id,
                    models.EventType.owner_id == owner_id,
                )
            )
        ).scalar_one_or_none()


def _values(data: EventTypeInput) -> dict[str, object]:
    return {
        "title": data.title,
        "description": data.description,
        "duration_min": data.duration_min,
        "slot_interval_min": data.slot_interval_min,
        "buffer_before_min": data.buffer_before_min,
        "buffer_after_min": data.buffer_after_min,
        "min_notice_min": data.min_notice_min,
        "date_window_days": data.date_window_days,
        "max_per_day": data.max_per_day,
        "location_type": data.location_type,
        "active": data.active,
    }


def _to_data(row: models.EventType, organization_slug: str) -> EventTypeData:
    return EventTypeData(
        id=row.id,
        organization_id=row.organization_id,
        organization_slug=organization_slug,
        slug=row.slug,
        title=row.title,
        description=row.description,
        duration_min=row.duration_min,
        slot_interval_min=row.slot_interval_min,
        buffer_before_min=row.buffer_before_min,
        buffer_after_min=row.buffer_after_min,
        min_notice_min=row.min_notice_min,
        date_window_days=row.date_window_days,
        max_per_day=row.max_per_day,
        location_type=row.location_type,
        active=row.active,
    )
