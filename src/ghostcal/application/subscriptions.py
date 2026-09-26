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
    blocks_availability: bool = False


@dataclass(frozen=True, slots=True)
class SubscriptionData:
    id: uuid.UUID
    name: str
    url: str
    color: str
    blocks_availability: bool
    status: str
    last_error: str | None
    last_synced_at: datetime | None


class SubscriptionRepository:
    async def add(self, owner_id: uuid.UUID, data: SubscriptionInput) -> uuid.UUID:
        raise NotImplementedError

    async def list_for_user(self, owner_id: uuid.UUID) -> list[SubscriptionData]:
        raise NotImplementedError

    async def set_blocking(
        self, subscription_id: uuid.UUID, owner_id: uuid.UUID, blocking: bool
    ) -> bool:
        raise NotImplementedError

    async def set_color(self, subscription_id: uuid.UUID, owner_id: uuid.UUID, color: str) -> bool:
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


async def set_subscription_blocking(
    repo: SubscriptionRepository, subscription_id: uuid.UUID, owner_id: uuid.UUID, blocking: bool
) -> None:
    """Ce calendrier abonné rend-il les créneaux non réservables ?

    Réglable après coup, et pas seulement à la création : quiconque avait déjà
    des abonnements devrait sinon les supprimer et les recréer — donc perdre
    leur couleur, leur place, et leur cache.
    """
    if not await repo.set_blocking(subscription_id, owner_id, blocking):
        raise SubscriptionNotFound(str(subscription_id))


async def set_subscription_color(
    repo: SubscriptionRepository, subscription_id: uuid.UUID, owner_id: uuid.UUID, color: str
) -> None:
    """Recolour a subscribed calendar after the fact.

    The docstring on `set_subscription_blocking` already named the cost of not having this: deleting
    and recreating a subscription to change one setting means "perdre leur couleur, leur place, et
    leur cache". The colour itself was the one setting still stuck at creation time.
    """
    if not await repo.set_color(subscription_id, owner_id, color):
        raise SubscriptionNotFound(str(subscription_id))
