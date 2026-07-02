"""Public ICS calendar subscription use cases: add/list/delete + refresh (fetch → cache events)."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from ghostcal.infrastructure.calendars.ics_feed import FeedEvent, IcsFeedError, fetch_feed

logger = logging.getLogger("ghostcal.subscriptions")


class SubscriptionError(Exception):
    pass


class SubscriptionNotFound(SubscriptionError):
    pass


class FeedUnreachable(SubscriptionError):
    pass


@dataclass(frozen=True, slots=True)
class SubscriptionInput:
    name: str
    url: str
    color: str


@dataclass(frozen=True, slots=True)
class SubscriptionData:
    id: uuid.UUID
    name: str
    url: str
    color: str
    status: str
    last_error: str | None
    last_synced_at: datetime | None


class SubscriptionRepository:
    async def add(self, owner_id: uuid.UUID, data: SubscriptionInput) -> uuid.UUID:
        raise NotImplementedError

    async def list_for_user(self, owner_id: uuid.UUID) -> list[SubscriptionData]:
        raise NotImplementedError

    async def get_url(self, subscription_id: uuid.UUID) -> str | None:
        raise NotImplementedError

    async def delete(self, subscription_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
        raise NotImplementedError

    async def owner_of(self, subscription_id: uuid.UUID) -> uuid.UUID | None:
        raise NotImplementedError

    async def replace_events(
        self, subscription_id: uuid.UUID, owner_id: uuid.UUID, events: list[FeedEvent]
    ) -> int:
        raise NotImplementedError

    async def mark_synced(self, subscription_id: uuid.UUID) -> None:
        raise NotImplementedError

    async def mark_error(self, subscription_id: uuid.UUID, message: str) -> None:
        raise NotImplementedError


async def add_subscription(
    repo: SubscriptionRepository, owner_id: uuid.UUID, data: SubscriptionInput
) -> uuid.UUID:
    # Verify the feed is reachable and parseable before saving (surfaces a bad URL immediately).
    try:
        await fetch_feed(data.url)
    except IcsFeedError as exc:
        raise FeedUnreachable(str(exc)) from exc
    return await repo.add(owner_id, data)


async def list_subscriptions(
    repo: SubscriptionRepository, owner_id: uuid.UUID
) -> list[SubscriptionData]:
    return await repo.list_for_user(owner_id)


async def delete_subscription(
    repo: SubscriptionRepository, subscription_id: uuid.UUID, owner_id: uuid.UUID
) -> None:
    if not await repo.delete(subscription_id, owner_id):
        raise SubscriptionNotFound(str(subscription_id))


async def refresh_subscription(repo: SubscriptionRepository, subscription_id: uuid.UUID) -> int:
    """Fetch the feed and replace its cached events. Returns how many events were stored."""
    owner_id = await repo.owner_of(subscription_id)
    url = await repo.get_url(subscription_id)
    if owner_id is None or url is None:
        raise SubscriptionNotFound(str(subscription_id))
    try:
        events = await fetch_feed(url)
    except IcsFeedError as exc:
        await repo.mark_error(subscription_id, str(exc))
        raise FeedUnreachable(str(exc)) from exc
    stored = await repo.replace_events(subscription_id, owner_id, events)
    await repo.mark_synced(subscription_id)
    return stored
