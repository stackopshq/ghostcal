"""Sign-up must survive the email provider, and must not get ahead of its own transaction.

Measured in production on 2026-09-25: `POST /v1/auth/register` answered 500 for every caller.
Brevo returned 401 (the server's egress address was not on its allow-list),
`sender.py:108 raise_for_status()` raised inside the route's `async with db_session()`, and the
transaction rolled back. Nothing was persisted -- `login` answered 401 afterwards and a second
attempt on the same address answered 500 rather than 409.

These tests are deliberately at the route level and not at `AuthService`, because the guarantee
lives in the composition: the transaction boundary is the route's `async with db_session()` block
(`db_session` wraps the body in `session.begin()`, and `SqlAuthRepository` never commits on its
own), so "after the commit" can only mean "after that block". A test of the service alone could
not tell a message queued too early from one queued at the right time.

No database and no broker: the session, the repository and the queue are all stand-ins whose only
job is to record the order in which they were used.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
import pytest
from fastapi import HTTPException

from ghostcal.application.auth import AuthUserRecord, EmailAlreadyRegistered, ZkKeyMaterial
from ghostcal.application.passwords import NoBreachCheck
from ghostcal.application.ports.email import Attachment
from ghostcal.infrastructure import tasks
from ghostcal.infrastructure.email.outbox import DeferredEmailSender, PendingEmail
from ghostcal.presentation import auth_routes
from ghostcal.presentation.schemas import ForgotPasswordIn, RegisterIn, ZkKeyMaterialIn

USER_ID = uuid.uuid4()
PASSWORD = "s3cret-passw0rd-long-enough"


def _register_payload(email: str = "alice@example.com") -> RegisterIn:
    return RegisterIn(
        email=email,
        name="Alice",
        password=PASSWORD,
        zk_keys=ZkKeyMaterialIn(
            public_key="cHVibGljLWtleQ==",
            wrapped_private_key="d3JhcHBlZC1zaw==",
            wrap_salt="c2FsdA==",
            recovery_wrapped_private_key="cmVjb3Zlcnktd3JhcHBlZA==",
            recovery_salt="cmVjb3Zlcnktc2FsdA==",
        ),
    )


def _fake_db_session(journal: list[str]):
    """A stand-in for `db_session` with the same commit/rollback semantics and no database.

    `session.begin()` commits when the block exits cleanly and rolls back when it does not; the
    journal records which happened, so a test can say where the commit fell relative to the queue.
    """

    @asynccontextmanager
    async def _session() -> AsyncIterator[object]:
        journal.append("begin")
        try:
            yield object()
        except BaseException:
            journal.append("rollback")
            raise
        journal.append("commit")

    return _session


def _fake_repository(
    journal: list[str],
    *,
    duplicate: bool = False,
    user: AuthUserRecord | None = None,
):
    class FakeAuthRepository:
        def __init__(self, session: object) -> None:
            self._session = session

        async def provision_account(
            self, *, email: str, name: str, password_hash: str, org_name: str, org_slug: str
        ) -> uuid.UUID:
            if duplicate:
                raise EmailAlreadyRegistered(email)
            journal.append("write:account")
            return USER_ID

        async def store_zk_keys(self, user_id: uuid.UUID, material: ZkKeyMaterial) -> None:
            journal.append("write:zk_keys")

        async def add_email_verification(
            self, user_id: uuid.UUID, token_hash: str, expires_at: datetime
        ) -> None:
            journal.append("write:verification_token")

        async def get_by_email(self, email: str) -> AuthUserRecord | None:
            return user

        async def add_password_reset(
            self, user_id: uuid.UUID, token_hash: str, expires_at: datetime
        ) -> None:
            journal.append("write:reset_token")

    return FakeAuthRepository


class ExplodingMailer:
    """What Brevo was on the morning of the incident: a 401 on every call.

    Installed as the module-level `_mailer` so that any regression which sends from inside the
    request path fails loudly here instead of quietly in production.
    """

    def __init__(self) -> None:
        self.calls = 0

    async def send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        attachments: Sequence[Attachment] | None = None,
    ) -> None:
        self.calls += 1
        raise httpx.HTTPStatusError(
            "401 Unauthorized",
            request=httpx.Request("POST", "https://api.brevo.com/v3/smtp/email"),
            response=httpx.Response(401),
        )


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> ExplodingMailer:
    """Neutralise everything the register route touches except what is under test."""
    mailer = ExplodingMailer()
    monkeypatch.setattr(auth_routes, "_mailer", mailer)
    # The real checker would reach api.pwnedpasswords.com; the policy itself still applies.
    monkeypatch.setattr(auth_routes, "_breach_checker", NoBreachCheck())
    return mailer


# --------------------------------------------------------------------------------------------
# The ordering trap: never queue a message the database cannot yet back.
# --------------------------------------------------------------------------------------------


async def test_the_verification_email_is_queued_only_after_the_commit(
    monkeypatch: pytest.MonkeyPatch, wired: ExplodingMailer
) -> None:
    journal: list[str] = []
    monkeypatch.setattr(auth_routes, "db_session", _fake_db_session(journal))
    monkeypatch.setattr(auth_routes, "SqlAuthRepository", _fake_repository(journal))
    monkeypatch.setattr(
        auth_routes, "enqueue_email", lambda message: journal.append("queue:send_email")
    )

    out = await auth_routes.register(_register_payload())

    assert out.user_id == USER_ID
    assert journal == [
        "begin",
        "write:account",
        "write:zk_keys",
        "write:verification_token",
        "commit",
        "queue:send_email",
    ], journal
    # A worker that read the database before that commit would find no verification row for the
    # token it was told to mail. Nothing in the request path spoke to the provider either.
    assert wired.calls == 0


async def test_nothing_is_queued_when_the_registration_is_rejected(
    monkeypatch: pytest.MonkeyPatch, wired: ExplodingMailer
) -> None:
    """A rolled-back sign-up must not produce a verification email for an account that never was."""
    journal: list[str] = []
    monkeypatch.setattr(auth_routes, "db_session", _fake_db_session(journal))
    monkeypatch.setattr(auth_routes, "SqlAuthRepository", _fake_repository(journal, duplicate=True))
    monkeypatch.setattr(
        auth_routes, "enqueue_email", lambda message: journal.append("queue:send_email")
    )

    with pytest.raises(HTTPException) as raised:
        await auth_routes.register(_register_payload())

    assert raised.value.status_code == 409
    assert "rollback" in journal
    assert "queue:send_email" not in journal


# --------------------------------------------------------------------------------------------
# The second dependency: a broker that is down may not cost anyone their account either.
# --------------------------------------------------------------------------------------------


async def test_registration_succeeds_when_the_queue_cannot_be_reached(
    monkeypatch: pytest.MonkeyPatch, wired: ExplodingMailer, caplog: pytest.LogCaptureFixture
) -> None:
    journal: list[str] = []
    monkeypatch.setattr(auth_routes, "db_session", _fake_db_session(journal))
    monkeypatch.setattr(auth_routes, "SqlAuthRepository", _fake_repository(journal))

    def _redis_is_down(message: PendingEmail) -> None:
        raise ConnectionError("Error 111 connecting to redis:6379. Connection refused.")

    monkeypatch.setattr(auth_routes, "enqueue_email", _redis_is_down)

    with caplog.at_level(logging.ERROR, logger="ghostcal.email"):
        out = await auth_routes.register(_register_payload())

    assert out.user_id == USER_ID
    assert "commit" in journal
    # Swapping a fatal dependency on Brevo for a fatal one on Redis would be no improvement -- but
    # neither is losing the email in silence. This is how an operator finds out.
    assert [r for r in caplog.records if r.levelno >= logging.ERROR], (
        "a dropped email left no trace in the logs"
    )
    assert "example.com" in caplog.text
    assert "alice@" not in caplog.text  # the domain is logged, the mailbox is not


async def test_forgot_password_keeps_its_promise_when_email_is_broken(
    monkeypatch: pytest.MonkeyPatch, wired: ExplodingMailer
) -> None:
    """`request_password_reset` says it "always returns as if it worked". Before this change it
    did not: for a known, verified address the provider's 401 propagated and the route answered
    500, while an unknown address still answered 202 -- an enumeration oracle assembled out of an
    outage.
    """
    journal: list[str] = []
    known = AuthUserRecord(
        id=USER_ID,
        email="alice@example.com",
        name="Alice",
        timezone="Europe/Zurich",
        email_verified=True,
        password_hash="argon2-whatever",
    )
    monkeypatch.setattr(auth_routes, "db_session", _fake_db_session(journal))
    monkeypatch.setattr(auth_routes, "SqlAuthRepository", _fake_repository(journal, user=known))
    monkeypatch.setattr(
        auth_routes, "enqueue_email", lambda message: journal.append("queue:send_email")
    )

    assert await auth_routes.forgot_password(ForgotPasswordIn(email="alice@example.com")) is None
    assert journal == [
        "begin",
        "write:reset_token",
        "commit",
        "queue:send_email",
    ], journal
    assert wired.calls == 0


# --------------------------------------------------------------------------------------------
# The buffer itself.
# --------------------------------------------------------------------------------------------


async def test_the_outbox_holds_the_message_until_it_is_told_to_let_go() -> None:
    handed: list[PendingEmail] = []
    outbox = DeferredEmailSender(handed.append)

    await outbox.send(to="bob@example.com", subject="Hello", html="<p>hi</p>")

    assert handed == []  # nothing has left while the caller's transaction may still roll back
    assert [m.subject for m in outbox.pending] == ["Hello"]

    result = outbox.hand_off()

    assert (result.queued, result.dropped, result.complete) == (1, 0, True)
    assert [m.to for m in handed] == ["bob@example.com"]
    assert outbox.pending == ()  # and not a second time


async def test_the_outbox_reports_partial_delivery_rather_than_success() -> None:
    """Three states, not two: some may go and some may not, and the caller can tell."""
    attempted: list[str] = []

    def _dispatch(message: PendingEmail) -> None:
        attempted.append(message.to)
        if message.to.endswith("@broken.invalid"):
            raise ConnectionError("broker refused")

    outbox = DeferredEmailSender(_dispatch)
    await outbox.send(to="ok@example.com", subject="a", html="a")
    await outbox.send(to="no@broken.invalid", subject="b", html="b")
    await outbox.send(to="also-ok@example.com", subject="c", html="c")

    result = outbox.hand_off()

    assert (result.queued, result.dropped) == (2, 1)
    assert result.complete is False
    # One failure must not abandon the messages behind it.
    assert len(attempted) == 3


# --------------------------------------------------------------------------------------------
# The worker end: which refusals are worth repeating.
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_transient_refusals_are_retried(status: int) -> None:
    assert tasks._is_worth_retrying(status) is True


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_settled_refusals_are_not_retried(status: int) -> None:
    """A 401 is the key, the sending domain or the egress address -- none of which change in ten
    seconds. This is the exact status that took sign-ups down; retrying it three times would have
    produced three identical failures and buried the one log line worth reading."""
    assert tasks._is_worth_retrying(status) is False


class _StatusMailer:
    def __init__(self, status: int) -> None:
        self._status = status

    async def send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        attachments: Sequence[Attachment] | None = None,
    ) -> None:
        raise httpx.HTTPStatusError(
            f"{self._status}",
            request=httpx.Request("POST", "https://api.brevo.com/v3/smtp/email"),
            response=httpx.Response(self._status),
        )


async def test_a_401_fails_the_task_instead_of_retrying_it(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(tasks, "_mailer", _StatusMailer(401))
    with (
        caplog.at_level(logging.ERROR, logger="ghostcal.tasks"),
        pytest.raises(tasks.EmailRefused),
    ):
        await tasks._send_email("alice@example.com", "Verify your GhostCal email", "<p>x</p>", [])
    # EmailRefused is not in `autoretry_for`, so the task ends FAILURE: counted on the worker's
    # celery_tasks{outcome="failure"} and logged by the task_failure handler.
    assert caplog.records
    assert "alice@" not in caplog.text


async def test_a_429_asks_celery_to_come_back_later(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks, "_mailer", _StatusMailer(429))
    with pytest.raises(tasks.EmailDeferred):
        await tasks._send_email("alice@example.com", "Verify your GhostCal email", "<p>x</p>", [])


async def test_an_unreachable_provider_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Unreachable:
        async def send(self, **_: object) -> None:
            raise httpx.ConnectTimeout("api.brevo.com timed out")

    monkeypatch.setattr(tasks, "_mailer", _Unreachable())
    with pytest.raises(tasks.EmailDeferred):
        await tasks._send_email("alice@example.com", "subject", "<p>x</p>", [])


async def test_attachments_survive_the_trip_through_the_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The port allows attachments and Celery's JSON serializer does not carry bytes. Dropping
    them silently would be the same class of bug as the rest of this file."""
    sent: list[tuple[str, bytes]] = []

    class _Recorder:
        async def send(
            self,
            *,
            to: str,
            subject: str,
            html: str,
            attachments: Sequence[Attachment] | None = None,
        ) -> None:
            sent.extend((a.filename, a.content) for a in attachments or ())

    monkeypatch.setattr(tasks, "_mailer", _Recorder())
    payload: list[dict[str, str]] = []
    monkeypatch.setattr(
        tasks.send_email, "delay", lambda *args: payload.append(args[3]), raising=False
    )

    tasks.enqueue_email(
        PendingEmail(
            to="bob@example.com",
            subject="Your booking",
            html="<p>x</p>",
            attachments=(Attachment(filename="invite.ics", content=b"BEGIN:VCALENDAR"),),
        )
    )
    await tasks._send_email("bob@example.com", "Your booking", "<p>x</p>", payload[0])

    assert sent == [("invite.ics", b"BEGIN:VCALENDAR")]
