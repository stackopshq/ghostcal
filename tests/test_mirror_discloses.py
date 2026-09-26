"""What a mirrored booking says on someone else's calendar.

This is the one place where GhostCal writes to a server it does not run. Until 2026-08-31 it wrote,
every time, without a setting and without a screen saying so:

    summary     = the event type's title
    description = "Booked via GhostCal · " + the invitee's email address

The invitee's address is the one field about them that is not sealed, and it was leaving the product
for a calendar hosted by Apple, Fastmail or whoever the host had connected — decided by neither the
host nor the invitee.

These tests assert on **what reaches the client**, not on what the caller passed. That
distinction is the whole point: both call sites still pass the detailed values, and the
redaction happens inside `mirror_booking`, where no future caller can forget it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from ghostcal.application.mirror import BUSY_SUMMARY, mirror_booking

INVITEE = "clara@example.test"
TITLE = "Job interview"
LOCATION = "Google Meet"
START = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


@dataclass
class FakeConnection:
    mirror_detail: str
    calendar_url: str = "https://caldav.example.test/cal/"
    server_url: str = "https://caldav.example.test/"
    username: str = "host@example.test"
    password_encrypted: str = "sealed"


@dataclass
class FakeConnRepo:
    conn: FakeConnection | None

    async def mirror_target(self, host_id: uuid.UUID) -> FakeConnection | None:
        return self.conn


@dataclass
class FakeSchedulingRepo:
    async def set_external_event(self, *args: Any, **kwargs: Any) -> None:
        return None


class FakeCipher:
    def decrypt(self, value: str) -> str:
        return "password"

    def encrypt(self, value: str) -> str:
        return "sealed"


@dataclass
class RecordingClient:
    """Stands in for the third party, and keeps exactly what it was handed."""

    sent: list[dict[str, Any]] = field(default_factory=list)

    async def create_event(self, creds: Any, calendar_url: str, **kwargs: Any) -> str:
        self.sent.append(kwargs)
        return "https://caldav.example.test/cal/event.ics"


async def _mirror(detail: str) -> dict[str, Any]:
    client = RecordingClient()
    await mirror_booking(
        FakeConnRepo(FakeConnection(mirror_detail=detail)),  # type: ignore[arg-type]
        FakeSchedulingRepo(),  # type: ignore[arg-type]
        FakeCipher(),  # type: ignore[arg-type]
        client,  # type: ignore[arg-type]
        host_id=uuid.uuid4(),
        booking_id=uuid.uuid4(),
        summary=TITLE,
        description=f"Booked via GhostCal · {INVITEE}",
        location=LOCATION,
        start=START,
        end=START + timedelta(minutes=30),
    )
    assert client.sent, "nothing reached the calendar, so this test proves nothing"
    return client.sent[0]


async def test_a_busy_mirror_carries_no_invitee_address() -> None:
    sent = await _mirror("busy")

    # The assertion that matters: the address is nowhere in what left, in any field.
    assert INVITEE not in " ".join(str(v) for v in sent.values())
    assert sent["summary"] == BUSY_SUMMARY
    assert sent["description"] == ""
    assert sent["location"] == ""


async def test_a_busy_mirror_carries_no_event_title_either() -> None:
    """A title is not neutral. "Job interview" on a shared work calendar says as much as a name."""
    sent = await _mirror("busy")
    assert TITLE not in " ".join(str(v) for v in sent.values())


async def test_the_slot_is_still_written_so_the_calendar_stays_correct() -> None:
    """Quiet, not absent: the host's availability must still be blocked."""
    sent = await _mirror("busy")
    assert sent["start"] == START
    assert sent["end"] == START + timedelta(minutes=30)


async def test_detailed_is_what_it_says() -> None:
    """A host who asked for the detail gets it — this is a choice, not a removal."""
    sent = await _mirror("detailed")
    assert sent["summary"] == TITLE
    assert INVITEE in sent["description"]
    assert sent["location"] == LOCATION


@pytest.mark.parametrize("detail", ["", "DETAILED", "verbose", "unknown-future-value"])
async def test_an_unrecognised_setting_says_less_rather_than_more(detail: str) -> None:
    """Only the exact word opens the detail.

    A value this build does not know — a newer setting, a typo, a half-finished migration — must
    never be read as permission to disclose. The failure has to fall on the quiet side.
    """
    sent = await _mirror(detail)
    assert INVITEE not in " ".join(str(v) for v in sent.values())
    assert sent["summary"] == BUSY_SUMMARY
