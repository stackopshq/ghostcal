"""Reminder dispatch against a live PostgreSQL: due offsets, idempotency, last-minute guard."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.reminders import dispatch_reminders
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.reminders_repository import SqlReminderGateway
from ghostcal.infrastructure.db.session import db_session

pytestmark = pytest.mark.integration

OFFSETS = (1440, 60)  # 24 h and 1 h


class CapturingMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    async def send(self, *, to: str, subject: str, html: str, attachments: object = None) -> None:
        self.sent.append({"to": to, "subject": subject})


async def _seed(engine: AsyncEngine) -> tuple[uuid.UUID, uuid.UUID]:
    """A confirmed booking 50 min out, booked 20 min ago, so only the 1 h reminder is due."""
    now = datetime.now(UTC)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        org = models.Organization(name="Rem Org", slug=f"rem-{uuid.uuid4().hex[:8]}")
        user = models.User(
            email=f"host-{uuid.uuid4().hex[:8]}@example.com", name="Host", timezone="UTC"
        )
        db.add_all([org, user])
        await db.flush()
        db.add(models.Membership(organization_id=org.id, user_id=user.id, role="owner"))
        event = models.EventType(
            organization_id=org.id,
            owner_id=user.id,
            slug=f"call-{uuid.uuid4().hex[:6]}",
            title="Intro Call",
            duration_min=30,
        )
        db.add(event)
        await db.flush()
        booking = models.Booking(
            organization_id=org.id,
            event_type_id=event.id,
            host_id=user.id,
            invitee_name="Invitee",
            invitee_email="invitee@example.com",
            invitee_timezone="UTC",
            start_at=now + timedelta(minutes=50),
            end_at=now + timedelta(minutes=80),
            status="confirmed",
            created_at=now - timedelta(minutes=20),
        )
        db.add(booking)
        await db.commit()
        return org.id, user.id


async def test_reminders_dispatch_once_and_skip_stale_offset(admin_engine: AsyncEngine) -> None:
    org_id, user_id = await _seed(admin_engine)
    try:
        mailer = CapturingMailer()
        async with db_session() as session:
            sent = await dispatch_reminders(SqlReminderGateway(session), mailer, offsets=OFFSETS)
        # Only the 1 h reminder is due; the 24 h one is skipped (booked 20 min ago).
        assert sent == 1
        assert len(mailer.sent) == 1
        assert "Reminder" in mailer.sent[0]["subject"]
        assert mailer.sent[0]["to"] == "invitee@example.com"

        # Running again sends nothing (already claimed) — exactly-once.
        async with db_session() as session:
            again = await dispatch_reminders(SqlReminderGateway(session), mailer, offsets=OFFSETS)
        assert again == 0

        async with async_sessionmaker(admin_engine)() as db:
            count = (
                await db.execute(
                    text("SELECT count(*) FROM booking_reminders WHERE organization_id = :o"),
                    {"o": org_id},
                )
            ).scalar()
        assert count == 1
    finally:
        async with async_sessionmaker(admin_engine)() as db:
            await db.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org_id})
            await db.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
            await db.commit()
