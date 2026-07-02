"""SQL implementation of the calendar-subscription repository port (org-scoped RLS session)."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.subscriptions import (
    SubscriptionData,
    SubscriptionInput,
    SubscriptionRepository,
)
from ghostcal.infrastructure.calendars.ics_feed import FeedEvent
from ghostcal.infrastructure.db import models


class SqlSubscriptionRepository(SubscriptionRepository):
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._org_id = organization_id

    async def add(self, owner_id: uuid.UUID, data: SubscriptionInput) -> uuid.UUID:
        return (
            await self._session.execute(
                insert(models.CalendarSubscription)
                .values(
                    organization_id=self._org_id,
                    owner_id=owner_id,
                    name=data.name,
                    url=data.url,
                    color=data.color,
                )
                .returning(models.CalendarSubscription.id)
            )
        ).scalar_one()

    async def list_for_user(self, owner_id: uuid.UUID) -> list[SubscriptionData]:
        rows = (
            await self._session.execute(
                select(
                    models.CalendarSubscription.id,
                    models.CalendarSubscription.name,
                    models.CalendarSubscription.url,
                    models.CalendarSubscription.color,
                    models.CalendarSubscription.status,
                    models.CalendarSubscription.last_error,
                    models.CalendarSubscription.last_synced_at,
                )
                .where(models.CalendarSubscription.owner_id == owner_id)
                .order_by(models.CalendarSubscription.created_at)
            )
        ).all()
        return [
            SubscriptionData(
                id=r.id,
                name=r.name,
                url=r.url,
                color=r.color,
                status=r.status,
                last_error=r.last_error,
                last_synced_at=r.last_synced_at,
            )
            for r in rows
        ]

    async def get_url(self, subscription_id: uuid.UUID) -> str | None:
        return (
            await self._session.execute(
                select(models.CalendarSubscription.url).where(
                    models.CalendarSubscription.id == subscription_id
                )
            )
        ).scalar_one_or_none()

    async def owner_of(self, subscription_id: uuid.UUID) -> uuid.UUID | None:
        return (
            await self._session.execute(
                select(models.CalendarSubscription.owner_id).where(
                    models.CalendarSubscription.id == subscription_id
                )
            )
        ).scalar_one_or_none()

    async def delete(self, subscription_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(models.CalendarSubscription).where(
                models.CalendarSubscription.id == subscription_id,
                models.CalendarSubscription.owner_id == owner_id,
            )
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def replace_events(
        self, subscription_id: uuid.UUID, owner_id: uuid.UUID, events: list[FeedEvent]
    ) -> int:
        await self._session.execute(
            delete(models.SubscriptionEvent).where(
                models.SubscriptionEvent.subscription_id == subscription_id
            )
        )
        if not events:
            return 0
        await self._session.execute(
            insert(models.SubscriptionEvent),
            [
                {
                    "organization_id": self._org_id,
                    "subscription_id": subscription_id,
                    "owner_id": owner_id,
                    "uid": e.uid,
                    "start_at": e.start_at,
                    "end_at": e.end_at,
                    "all_day": e.all_day,
                    "summary": e.summary,
                }
                for e in events
            ],
        )
        return len(events)

    async def mark_synced(self, subscription_id: uuid.UUID) -> None:
        await self._session.execute(
            update(models.CalendarSubscription)
            .where(models.CalendarSubscription.id == subscription_id)
            .values(status="active", last_error=None, last_synced_at=func.now())
        )

    async def mark_error(self, subscription_id: uuid.UUID, message: str) -> None:
        await self._session.execute(
            update(models.CalendarSubscription)
            .where(models.CalendarSubscription.id == subscription_id)
            .values(status="error", last_error=message[:2000])
        )
