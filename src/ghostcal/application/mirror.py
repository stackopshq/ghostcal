"""Mirror bookings onto the host's external (CalDAV) calendar — best-effort write-back."""

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
    conn = await conn_repo.get(host_id)
    if conn is None:
        return
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
    conn = await conn_repo.get(host_id)
    if conn is None:
        return
    await client.delete_event(_credentials(conn, cipher), conn.calendar_url, external_event_uid)
