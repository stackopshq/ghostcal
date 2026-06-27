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
    questions_from_json,
    questions_to_json,
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
        pools = await self._pools([r.id for r in rows])
        return [_to_data(r, org_slug, pools.get(r.id, ())) for r in rows]

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
        pools = await self._pools([row.id])
        return _to_data(row, await self._org_slug(), pools.get(row.id, ()))

    async def _pools(
        self, event_type_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[uuid.UUID, ...]]:
        """Host pools for several event types, in stable (insertion) order."""
        if not event_type_ids:
            return {}
        rows = (
            await self._session.execute(
                select(models.EventTypeHost.event_type_id, models.EventTypeHost.user_id)
                .where(models.EventTypeHost.event_type_id.in_(event_type_ids))
                .order_by(models.EventTypeHost.created_at)
            )
        ).all()
        pools: dict[uuid.UUID, tuple[uuid.UUID, ...]] = {}
        for event_type_id, user_id in rows:
            pools[event_type_id] = (*pools.get(event_type_id, ()), user_id)
        return pools

    async def _replace_pool(
        self, event_type_id: uuid.UUID, host_ids: tuple[uuid.UUID, ...]
    ) -> None:
        await self._session.execute(
            delete(models.EventTypeHost).where(models.EventTypeHost.event_type_id == event_type_id)
        )
        for user_id in dict.fromkeys(host_ids):  # de-dupe, keep order
            await self._session.execute(
                insert(models.EventTypeHost).values(
                    organization_id=self._org_id,
                    event_type_id=event_type_id,
                    user_id=user_id,
                )
            )

    async def non_member_hosts(self, host_ids: tuple[uuid.UUID, ...]) -> set[uuid.UUID]:
        """host_ids that are NOT members of this organization (round-robin pool validation)."""
        if not host_ids:
            return set()
        members = (
            (
                await self._session.execute(
                    select(models.Membership.user_id).where(
                        models.Membership.organization_id == self._org_id,
                        models.Membership.user_id.in_(host_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        return set(host_ids) - set(members)

    async def _org_slug(self) -> str:
        return (
            await self._session.execute(
                select(models.Organization.slug).where(models.Organization.id == self._org_id)
            )
        ).scalar_one()

    async def create(self, owner_id: uuid.UUID, slug: str, data: EventTypeInput) -> uuid.UUID:
        event_type_id = (
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
        if data.kind == "round_robin":
            await self._replace_pool(event_type_id, data.host_ids)
        return event_type_id

    async def update(
        self, event_type_id: uuid.UUID, owner_id: uuid.UUID, data: EventTypeInput
    ) -> bool:
        row = await self._owned(event_type_id, owner_id)
        if row is None:
            return False
        for field, value in _values(data).items():
            setattr(row, field, value)
        await self._session.flush()
        # Keep the pool in sync with the kind: round-robin owns a pool, others have none.
        await self._replace_pool(event_type_id, data.host_ids if data.kind == "round_robin" else ())
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
        "kind": data.kind,
        "booking_questions": questions_to_json(data.questions),
    }


def _to_data(
    row: models.EventType,
    organization_slug: str,
    host_ids: tuple[uuid.UUID, ...] = (),
) -> EventTypeData:
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
        questions=questions_from_json(row.booking_questions),
        kind=row.kind,
        host_ids=host_ids,
    )
