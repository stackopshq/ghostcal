"""Free-busy links against a live PostgreSQL.

The point of this feature is what it *does not* say. So that is what these test.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.links import hash_token, new_token
from ghostcal.infrastructure.db import models
from ghostcal.presentation.api import app

pytestmark = pytest.mark.integration

SECRET_TITLE = "Interview at a competitor"


async def _seed(engine: AsyncEngine) -> tuple[uuid.UUID, str]:
    """One user, one calendar, two touching meetings and one apart. Returns (org, token)."""
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        row = (
            await s.execute(
                text(
                    "SELECT user_id, organization_id FROM "
                    "provision_account(:email, :name, :pw, :org, :slug)"
                ),
                {
                    "email": f"busy-{suffix}@example.test",
                    "name": "Ada Lovelace",
                    "pw": "x",
                    "org": "Ada",
                    "slug": f"busy-{suffix}",
                },
            )
        ).one()
        user_id, org_id = row.user_id, row.organization_id

        calendar = models.Calendar(organization_id=org_id, owner_id=user_id, name="Personal")
        s.add(calendar)
        await s.flush()

        base = datetime.now(UTC).replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(
            days=1
        )
        for start, end in (
            (base, base + timedelta(hours=1)),
            (base + timedelta(hours=1), base + timedelta(hours=2)),  # touches the first
            (base + timedelta(hours=5), base + timedelta(hours=6)),  # a real gap before this
        ):
            s.add(
                models.CalendarEvent(
                    organization_id=org_id,
                    owner_id=user_id,
                    calendar_id=calendar.id,
                    start_at=start,
                    end_at=end,
                    timezone="UTC",
                    # In the real system this is ciphertext. Here it is the plainest possible
                    # cleartext, so that a leak would be unmissable.
                    content=SECRET_TITLE,
                )
            )

        token = new_token()
        s.add(
            models.BusyLink(
                organization_id=org_id,
                user_id=user_id,
                token_hash=hash_token(token),
                name="My availability",
            )
        )
        await s.commit()
    return org_id, token


async def test_a_visitor_sees_when_never_what(admin_engine: AsyncEngine) -> None:
    _, token = await _seed(admin_engine)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/v1/public/busy/{token}")

    assert response.status_code == 200
    body = response.json()

    # The whole feature, in one assertion: the title is nowhere in the response. Not in a field we
    # forgot to strip, not in an error, not anywhere.
    assert SECRET_TITLE not in response.text
    assert body["owner_name"] == "Ada Lovelace"

    # And there is no field it could ever hide in.
    assert set(body["busy"][0]) == {"start_at", "end_at"}


async def test_touching_meetings_come_back_as_one_block(admin_engine: AsyncEngine) -> None:
    """Two back-to-back meetings are one unbroken stretch of busy. Reporting them separately would
    say "there is a seam here", which is more than "busy" — and more than was asked for."""
    _, token = await _seed(admin_engine)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        body = (await client.get(f"/v1/public/busy/{token}")).json()

    assert len(body["busy"]) == 2  # three meetings, two of them merged
    first = body["busy"][0]
    assert datetime.fromisoformat(first["end_at"]) - datetime.fromisoformat(
        first["start_at"]
    ) == timedelta(hours=2)


async def test_an_unknown_token_is_not_a_calendar(admin_engine: AsyncEngine) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/v1/public/busy/{new_token()}")
    assert response.status_code == 404


async def test_revoking_the_link_closes_the_door(admin_engine: AsyncEngine) -> None:
    _org, token = await _seed(admin_engine)

    async with async_sessionmaker(admin_engine)() as s:
        await s.execute(
            text("DELETE FROM busy_links WHERE token_hash = :h"), {"h": hash_token(token)}
        )
        await s.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/v1/public/busy/{token}")
    assert response.status_code == 404


async def test_the_calendar_feed_says_when_and_never_what(admin_engine: AsyncEngine) -> None:
    """The same link, subscribed to instead of read — and just as silent.

    A subscription is the shape that works here: a subscribed calendar carries VEVENT
    happily. The risk it brings is different from the JSON view's — an .ics is copied
    into other people's calendars, exported, forwarded — so the assertion is the same
    one, made against the bytes that travel.
    """
    _, token = await _seed(admin_engine)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/v1/public/busy/{token}/calendar.ics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    body = response.text

    # The title is nowhere in the bytes, and neither is any field that could carry one.
    assert SECRET_TITLE not in body
    for field in ("DESCRIPTION", "LOCATION", "ATTENDEE", "ORGANIZER", "X-ALT-DESC"):
        assert field not in body, f"{field} has no business in a free-busy feed"

    assert "BEGIN:VCALENDAR" in body and "END:VCALENDAR" in body
    assert body.count("BEGIN:VEVENT") == body.count("END:VEVENT") >= 1
    assert "SUMMARY:Occupé" in body

    # A cached copy outlives the revocation meant to end it.
    assert "no-store" in response.headers.get("cache-control", "")


async def test_the_feed_is_byte_identical_across_polls(admin_engine: AsyncEngine) -> None:
    """Nothing in the feed may read the clock.

    A DTSTAMP taken from `now` would change on every request, so every ETag would change,
    and every subscriber would re-download the whole calendar every quarter of an hour
    forever. The bytes must depend only on the busy time itself.
    """
    _, token = await _seed(admin_engine)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = (await client.get(f"/v1/public/busy/{token}/calendar.ics")).text
        second = (await client.get(f"/v1/public/busy/{token}/calendar.ics")).text

    assert first == second


async def test_two_links_do_not_agree_on_uids(admin_engine: AsyncEngine) -> None:
    """Holding one link must not let you confirm what another publishes.

    UIDs are keyed on the link, so the same hour published twice produces two unrelated
    identifiers. Without this, a recipient could correlate feeds — which is a different
    disclosure from "when am I busy", and one nobody agreed to.
    """
    _, first_token = await _seed(admin_engine)
    _, second_token = await _seed(admin_engine)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = (await client.get(f"/v1/public/busy/{first_token}/calendar.ics")).text
        second = (await client.get(f"/v1/public/busy/{second_token}/calendar.ics")).text

    def uids(text: str) -> set[str]:
        return {line for line in text.splitlines() if line.startswith("UID:")}

    assert uids(first) and uids(second)
    assert not (uids(first) & uids(second))


async def test_an_unknown_token_is_not_a_calendar_either(admin_engine: AsyncEngine) -> None:
    """The .ics door refuses exactly like the JSON one. A representation is not a bypass."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/v1/public/busy/{new_token()}/calendar.ics")

    assert response.status_code == 404
