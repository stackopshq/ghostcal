"""Mirror bookings onto the host's external (CalDAV) calendar — best-effort write-back.

A host may have several calendars connected. Bookings go to exactly one of them — the mirror target
— because writing each meeting to every connected calendar would duplicate it. Which one that is
lives in the database (``caldav_connections.mirror_bookings``, a partial unique index), not in a
guess made here.

**What the mirror discloses is decided here and nowhere else.** Until 2026-08-31 it wrote the event
title and, in the description, the invitee's email address — onto a calendar hosted by Apple,
Fastmail or whoever the host connected. That address is the one field of an invitee that is not
sealed, and it left the product through a convenience nobody had chosen. `mirror_detail` now governs
it, and the redaction happens inside `mirror_booking` rather than at its call sites: there are two
callers today, a third would forget, and forgetting means an address at a third party.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from ghostcal.application.calendars import CaldavConnectionRepository, SecretCipher
from ghostcal.application.ports.calendar import CalendarClient, CalendarCredentials
from ghostcal.application.scheduling import SchedulingRepository


def _credentials(conn: object, cipher: SecretCipher) -> CalendarCredentials:
    return CalendarCredentials(
        server_url=conn.server_url,  # type: ignore[attr-defined]
        username=conn.username,  # type: ignore[attr-defined]
        password=cipher.decrypt(conn.password_encrypted),  # type: ignore[attr-defined]
    )


def mirror_uid(booking_id: uuid.UUID) -> str:
    return f"ghostcal-{booking_id}"


# What a 'busy' mirror says. Deliberately not the event title: a title like "Job interview" on a
# shared work calendar discloses as much as a name would.
BUSY_SUMMARY = "Busy"


def _disclosed(
    detail: str, *, summary: str, description: str, location: str
) -> tuple[str, str, str]:
    """The three fields as they will leave the product.

    'detailed' is what a host explicitly asked for; anything else — including a value this build
    does not recognise — falls back to the quiet form. An unknown setting must never be read as
    permission to say more.
    """
    if detail == "detailed":
        return summary, description, location
    return BUSY_SUMMARY, "", ""


async def mirror_booking(
    conn_repo: CaldavConnectionRepository,
    scheduling_repo: SchedulingRepository,
    cipher: SecretCipher,
    client: CalendarClient,
    *,
    host_id: uuid.UUID,
    booking_id: uuid.UUID,
    summary: str,
    description: str,
    location: str,
    start: datetime,
    end: datetime,
) -> None:
    conn = await conn_repo.mirror_target(host_id)
    if conn is None:
        return
    summary, description, location = _disclosed(
        conn.mirror_detail, summary=summary, description=description, location=location
    )
    uid = mirror_uid(booking_id)
    url = await client.create_event(
        _credentials(conn, cipher),
        conn.calendar_url,
        uid=uid,
        summary=summary,
        description=description,
        location=location,
        start=start,
        end=end,
    )
    await scheduling_repo.set_external_event(booking_id, uid, url)


async def unmirror_booking(
    conn_repo: CaldavConnectionRepository,
    cipher: SecretCipher,
    client: CalendarClient,
    *,
    host_id: uuid.UUID,
    external_event_uid: str | None,
) -> None:
    if external_event_uid is None:
        return
    conn = await conn_repo.mirror_target(host_id)
    if conn is None:
        return
    await client.delete_event(_credentials(conn, cipher), conn.calendar_url, external_event_uid)
