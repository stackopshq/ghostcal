"""SQL implementation of the calendar-subscription repository port (org-scoped RLS session)."""

from __future__ import annotations

import logging
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

logger = logging.getLogger("ghostcal.subscriptions")


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
                    blocks_availability=data.blocks_availability,
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
                    models.CalendarSubscription.blocks_availability,
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
                blocks_availability=r.blocks_availability,
                status=r.status,
                last_error=r.last_error,
                last_synced_at=r.last_synced_at,
            )
            for r in rows
        ]

    async def set_blocking(
        self, subscription_id: uuid.UUID, owner_id: uuid.UUID, blocking: bool
    ) -> bool:
        """Bascule un abonnement existant.

        Sans ça, un utilisateur qui a déjà ses calendriers devrait les
        supprimer et les recréer pour profiter du réglage — c'est-à-dire
        perdre leur couleur et leur place. Le filtre sur `owner_id` est ce qui
        empêche de basculer l'abonnement de quelqu'un d'autre.
        """
        # `returning(id)` plutôt que `rowcount` : le typage de SQLAlchemy ne
        # promet pas cet attribut sur un `Result`, et une valeur qui n'existe
        # que par convention est ce qui casse au prochain changement de version.
        row = (
            await self._session.execute(
                update(models.CalendarSubscription)
                .where(
                    models.CalendarSubscription.id == subscription_id,
                    models.CalendarSubscription.owner_id == owner_id,
                )
                .values(blocks_availability=blocking)
                .returning(models.CalendarSubscription.id)
            )
        ).scalar_one_or_none()
        return row is not None

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
        # Dernier recours contre la clé d'unicité, et il doit exister même
        # maintenant que `recurrence_id` en fait partie : ce qui arrive ici
        # vient d'un tiers, et **aucun flux tiers ne doit pouvoir renvoyer 500
        # à l'utilisateur**. Un agenda qui répète deux fois le même couple
        # (uid, recurrence_id) est malformé ; on garde la dernière occurrence
        # et on continue, plutôt que de refuser tout l'abonnement pour une
        # ligne. Sans ce filet, la contrainte transforme la donnée d'autrui en
        # panne de notre côté — ce qui s'est produit le 2026-08-14.
        unique = {(e.uid, e.recurrence_id): e for e in events}
        rows = list(unique.values())
        if len(rows) != len(events):
            logger.info(
                "subscription %s: %d duplicate (uid, recurrence_id) dropped from feed",
                subscription_id,
                len(events) - len(rows),
            )
        await self._session.execute(
            insert(models.SubscriptionEvent),
            [
                {
                    "organization_id": self._org_id,
                    "subscription_id": subscription_id,
                    "owner_id": owner_id,
                    "uid": e.uid,
                    "recurrence_id": e.recurrence_id,
                    "start_at": e.start_at,
                    "end_at": e.end_at,
                    "all_day": e.all_day,
                    "summary": e.summary,
                }
                for e in rows
            ],
        )
        return len(rows)

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
