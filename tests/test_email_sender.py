"""Which provider ghostcal picks, and the shape it posts to each.

Written after the estate discovered that the deployed image had no SMTP branch at all
while its Ansible role rendered five `GHOSTCAL_SMTP_*` variables and asserted on an SMTP
password. Nothing read them, and a mail route that looks configured is worse than one
that is plainly absent — so the selection logic is now pinned by tests rather than by a
comment.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from ghostcal.application.ports.email import Attachment
from ghostcal.config import Settings
from ghostcal.infrastructure.email.sender import (
    BrevoEmailSender,
    LogEmailSender,
    ResendEmailSender,
    build_email_sender,
)


def _settings(**overrides: Any) -> Settings:
    champs: dict[str, Any] = {
        "brevo_api_key": None,
        "resend_api_key": None,
        "email_from": "GhostCal <noreply@stackops.ch>",
    }
    champs.update(overrides)
    # `model_construct` skips validation on purpose: this module is about which provider
    # gets picked, not about whether the rest of a full Settings is well-formed.
    return Settings.model_construct(**champs)


def test_no_key_falls_back_to_logging() -> None:
    assert isinstance(build_email_sender(_settings()), LogEmailSender)


def test_resend_is_used_when_it_is_the_only_key() -> None:
    sender = build_email_sender(_settings(resend_api_key=SecretStr("re_x")))
    assert isinstance(sender, ResendEmailSender)


def test_brevo_wins_over_resend() -> None:
    """Brevo is the provider the sending domain is authenticated with.

    Under DMARC p=reject, a message no provider has signed for the domain is rejected
    outright. Preferring the unauthenticated provider would not degrade delivery — it
    would stop it.
    """
    sender = build_email_sender(
        _settings(brevo_api_key=SecretStr("xkeysib_x"), resend_api_key=SecretStr("re_x"))
    )
    assert isinstance(sender, BrevoEmailSender)


def _capture(monkeypatch: pytest.MonkeyPatch, seen: dict[str, Any]) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["json"] = __import__("json").loads(request.content)
        return httpx.Response(201, json={"messageId": "1"})

    original = httpx.AsyncClient

    def patched(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)


async def test_brevo_splits_the_sender_and_uses_its_own_field_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Brevo takes a structured sender where Resend takes the RFC 5322 string.

    Passing `GhostCal <noreply@…>` through unsplit is rejected by the API, so the same
    `email_from` setting has to be parsed for this provider and not for the other.
    """
    seen: dict[str, Any] = {}
    _capture(monkeypatch, seen)

    await BrevoEmailSender("xkeysib_x", "GhostCal <noreply@stackops.ch>").send(
        to="invitee@example.org",
        subject="Confirmation",
        html="<p>ok</p>",
        attachments=[Attachment(filename="invite.ics", content=b"BEGIN:VCALENDAR")],
    )

    assert seen["url"] == "https://api.brevo.com/v3/smtp/email"
    assert seen["headers"]["api-key"] == "xkeysib_x"
    assert "authorization" not in seen["headers"]
    assert seen["json"]["sender"] == {"email": "noreply@stackops.ch", "name": "GhostCal"}
    assert seen["json"]["to"] == [{"email": "invitee@example.org"}]
    # `htmlContent`, and `attachment` singular with `name` — Brevo's shape, not Resend's.
    assert seen["json"]["htmlContent"] == "<p>ok</p>"
    assert seen["json"]["attachment"][0]["name"] == "invite.ics"
    assert "html" not in seen["json"]
    assert "attachments" not in seen["json"]


async def test_brevo_accepts_a_bare_address_as_sender(monkeypatch: pytest.MonkeyPatch) -> None:
    """`email_from` is not required to carry a display name."""
    seen: dict[str, Any] = {}
    _capture(monkeypatch, seen)

    await BrevoEmailSender("k", "noreply@stackops.ch").send(
        to="invitee@example.org", subject="s", html="<p>h</p>"
    )

    assert seen["json"]["sender"] == {"email": "noreply@stackops.ch"}


async def test_brevo_raises_on_a_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A refused send must surface, not be swallowed — the caller retries on it."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": "unauthorized"})

    original = httpx.AsyncClient

    def patched(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)

    with pytest.raises(httpx.HTTPStatusError):
        await BrevoEmailSender("k", "noreply@stackops.ch").send(
            to="invitee@example.org", subject="s", html="<p>h</p>"
        )
