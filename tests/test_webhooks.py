"""Unit tests for webhook validation and payload signing."""

from __future__ import annotations

import hashlib
import hmac

import pytest

from ghostcal.application.webhooks import (
    InvalidWebhook,
    WebhookRepository,
    create_webhook,
    sign_payload,
)


class _FakeRepo(WebhookRepository):
    def __init__(self) -> None:
        self.created: dict[str, object] | None = None

    async def create(self, *, url, event_types, secret):  # type: ignore[no-untyped-def]
        import uuid

        self.created = {"url": url, "event_types": event_types, "secret": secret}
        return uuid.uuid4()


def test_sign_payload_is_hmac_sha256() -> None:
    body = b'{"event":"booking.created"}'
    expected = hmac.new(b"whsec_x", body, hashlib.sha256).hexdigest()
    assert sign_payload("whsec_x", body) == expected


async def test_create_rejects_non_http_url() -> None:
    with pytest.raises(InvalidWebhook):
        await create_webhook(_FakeRepo(), url="ftp://x.test", event_types=("booking.created",))


async def test_create_rejects_unknown_event() -> None:
    with pytest.raises(InvalidWebhook):
        await create_webhook(
            _FakeRepo(), url="https://x.test/hook", event_types=("booking.exploded",)
        )


async def test_create_generates_secret_and_dedupes_events() -> None:
    repo = _FakeRepo()
    created = await create_webhook(
        repo,
        url="https://x.test/hook",
        event_types=("booking.created", "booking.created", "booking.cancelled"),
    )
    assert created.secret.startswith("whsec_")
    assert created.event_types == ("booking.created", "booking.cancelled")
