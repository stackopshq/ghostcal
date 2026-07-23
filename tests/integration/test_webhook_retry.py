"""Which webhook failures are worth retrying (live PostgreSQL for the endpoint rows).

A 500 from a subscriber used to be logged once and the event was gone forever — webhooks were
unreliable in exactly the situation subscribers most need them to be reliable. Retrying everything
is the opposite mistake: a 4xx is the subscriber saying no, and repeating it just repeats the
argument.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.tasks import WebhookDeliveryIncomplete, _deliver_webhooks

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def org_with_endpoint(admin_engine: AsyncEngine) -> AsyncIterator[uuid.UUID]:
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        org = models.Organization(name="Org", slug=f"wh-{suffix}")
        s.add(org)
        await s.flush()
        s.add(
            models.WebhookEndpoint(
                organization_id=org.id,
                # A public IP literal: the SSRF guard accepts it without a DNS lookup, so
                # this test does not depend on name resolution. The transport is mocked.
                url="https://1.1.1.1/hook",
                secret="s3cret",
                event_types=["booking.created"],
                active=True,
            )
        )
        await s.commit()
        org_id = org.id
    try:
        yield org_id
    finally:
        async with maker() as s:
            await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org_id})
            await s.commit()


def _responding(status: int) -> httpx.MockTransport:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status)

    return httpx.MockTransport(handler)


async def _deliver(org_id: uuid.UUID, transport: httpx.MockTransport) -> int:
    original = httpx.AsyncClient

    def patched(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)  # type: ignore[arg-type]

    httpx.AsyncClient = patched  # type: ignore[misc,assignment]
    try:
        return await _deliver_webhooks(org_id, "booking.created", {"id": "x"}, "evt-1")
    finally:
        httpx.AsyncClient = original  # type: ignore[misc]


async def test_a_server_error_is_retried(org_with_endpoint: uuid.UUID) -> None:
    with pytest.raises(WebhookDeliveryIncomplete):
        await _deliver(org_with_endpoint, _responding(500))


async def test_throttling_is_retried(org_with_endpoint: uuid.UUID) -> None:
    with pytest.raises(WebhookDeliveryIncomplete):
        await _deliver(org_with_endpoint, _responding(429))


async def test_a_client_error_is_not_retried(org_with_endpoint: uuid.UUID) -> None:
    # 400/404 mean the subscriber has rejected this. Retrying wastes both sides' time and, with
    # backoff, keeps a broken endpoint in the queue for the better part of an hour.
    delivered = await _deliver(org_with_endpoint, _responding(400))
    assert delivered == 0


async def test_a_success_delivers_and_does_not_retry(org_with_endpoint: uuid.UUID) -> None:
    assert await _deliver(org_with_endpoint, _responding(200)) == 1
