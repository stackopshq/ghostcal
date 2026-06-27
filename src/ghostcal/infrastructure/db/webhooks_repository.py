"""SQL implementation of the webhook repository (org-scoped; RLS via org_session)."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.webhooks import (
    WebhookEndpointData,
    WebhookRepository,
    WebhookTarget,
)
from ghostcal.infrastructure.db import models


class SqlWebhookRepository(WebhookRepository):
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._org_id = organization_id

    async def create(self, *, url: str, event_types: tuple[str, ...], secret: str) -> uuid.UUID:
        return (
            await self._session.execute(
                insert(models.WebhookEndpoint)
                .values(
                    organization_id=self._org_id,
                    url=url,
                    secret=secret,
                    event_types=list(event_types),
                    active=True,
                )
                .returning(models.WebhookEndpoint.id)
            )
        ).scalar_one()

    async def list_all(self) -> list[WebhookEndpointData]:
        rows = (
            (
                await self._session.execute(
                    select(models.WebhookEndpoint).order_by(models.WebhookEndpoint.created_at)
                )
            )
            .scalars()
            .all()
        )
        return [
            WebhookEndpointData(
                id=r.id,
                url=r.url,
                event_types=tuple(r.event_types),
                active=r.active,
                created_at=r.created_at,
            )
            for r in rows
        ]

    async def delete(self, endpoint_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(models.WebhookEndpoint)
            .where(models.WebhookEndpoint.id == endpoint_id)
            .returning(models.WebhookEndpoint.id)
        )
        return result.first() is not None

    async def targets_for_event(self, event_type: str) -> list[WebhookTarget]:
        rows = (
            (
                await self._session.execute(
                    select(models.WebhookEndpoint).where(
                        models.WebhookEndpoint.active.is_(True),
                        models.WebhookEndpoint.event_types.contains([event_type]),
                    )
                )
            )
            .scalars()
            .all()
        )
        return [WebhookTarget(url=r.url, secret=r.secret) for r in rows]
