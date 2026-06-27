"""Webhook endpoints against a live PostgreSQL: create, event filtering, delete."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.webhooks import create_webhook, delete_webhook, list_webhooks
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.session import org_session
from ghostcal.infrastructure.db.webhooks_repository import SqlWebhookRepository

pytestmark = pytest.mark.integration


def _repo(session: object, org_id: uuid.UUID) -> SqlWebhookRepository:
    return SqlWebhookRepository(session, org_id)  # type: ignore[arg-type]


async def test_webhook_crud_and_event_filter(admin_engine: AsyncEngine) -> None:
    org_id = None
    try:
        async with async_sessionmaker(admin_engine, expire_on_commit=False)() as db:
            org = models.Organization(name="WH Org", slug=f"wh-{uuid.uuid4().hex[:8]}")
            db.add(org)
            await db.commit()
            org_id = org.id

        async with org_session(org_id) as session:
            created = await create_webhook(
                _repo(session, org_id),
                url="https://example.test/hook",
                event_types=("booking.created", "booking.cancelled"),
            )
        assert created.secret.startswith("whsec_")

        async with org_session(org_id) as session:
            endpoints = await list_webhooks(_repo(session, org_id))
        assert len(endpoints) == 1
        assert set(endpoints[0].event_types) == {"booking.created", "booking.cancelled"}

        # Only endpoints subscribed to the event are returned (with their secret).
        async with org_session(org_id) as session:
            targets = await _repo(session, org_id).targets_for_event("booking.created")
        assert len(targets) == 1
        assert targets[0].url == "https://example.test/hook"
        async with org_session(org_id) as session:
            none = await _repo(session, org_id).targets_for_event("poll.finalized")
        assert none == []

        async with org_session(org_id) as session:
            await delete_webhook(_repo(session, org_id), created.id)
        async with org_session(org_id) as session:
            assert await list_webhooks(_repo(session, org_id)) == []
    finally:
        if org_id is not None:
            async with async_sessionmaker(admin_engine)() as db:
                await db.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org_id})
                await db.commit()
