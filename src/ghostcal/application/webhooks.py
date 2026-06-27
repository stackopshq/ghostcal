"""Outbound webhook use cases: manage endpoints and sign delivered payloads.

Delivery itself runs in a Celery task (see infrastructure.tasks); these are the host-facing CRUD
operations plus the HMAC signing helper shared by the task.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

WEBHOOK_EVENTS = (
    "booking.created",
    "booking.cancelled",
    "booking.rescheduled",
    "poll.finalized",
)


class WebhookError(Exception):
    """Base class for webhook errors."""


class InvalidWebhook(WebhookError):
    pass


class WebhookNotFound(WebhookError):
    pass


@dataclass(frozen=True, slots=True)
class WebhookEndpointData:
    id: uuid.UUID
    url: str
    event_types: tuple[str, ...]
    active: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class WebhookCreated:
    id: uuid.UUID
    url: str
    event_types: tuple[str, ...]
    secret: str  # shown once, on creation


@dataclass(frozen=True, slots=True)
class WebhookTarget:
    url: str
    secret: str


class WebhookRepository:
    async def create(self, *, url: str, event_types: tuple[str, ...], secret: str) -> uuid.UUID:
        raise NotImplementedError

    async def list_all(self) -> list[WebhookEndpointData]:
        raise NotImplementedError

    async def delete(self, endpoint_id: uuid.UUID) -> bool:
        raise NotImplementedError

    async def targets_for_event(self, event_type: str) -> list[WebhookTarget]:
        """Active endpoints subscribed to ``event_type`` (url + secret)."""
        raise NotImplementedError


def sign_payload(secret: str, body: bytes) -> str:
    """Hex HMAC-SHA256 of the body, sent as the X-GhostCal-Signature header (``sha256=<hex>``)."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _validate(url: str, event_types: tuple[str, ...]) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise InvalidWebhook("url must be an absolute http(s) URL")
    if not event_types:
        raise InvalidWebhook("subscribe to at least one event")
    unknown = set(event_types) - set(WEBHOOK_EVENTS)
    if unknown:
        raise InvalidWebhook(f"unknown event(s): {', '.join(sorted(unknown))}")


async def create_webhook(
    repo: WebhookRepository, *, url: str, event_types: tuple[str, ...]
) -> WebhookCreated:
    events = tuple(dict.fromkeys(event_types))  # de-dupe, keep order
    _validate(url, events)
    secret = f"whsec_{secrets.token_urlsafe(32)}"
    endpoint_id = await repo.create(url=url, event_types=events, secret=secret)
    return WebhookCreated(id=endpoint_id, url=url, event_types=events, secret=secret)


async def list_webhooks(repo: WebhookRepository) -> list[WebhookEndpointData]:
    return await repo.list_all()


async def delete_webhook(repo: WebhookRepository, endpoint_id: uuid.UUID) -> None:
    if not await repo.delete(endpoint_id):
        raise WebhookNotFound(str(endpoint_id))
