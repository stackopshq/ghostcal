"""Deleting a mirrored event must not depend on the server honouring a UID search.

Measured on 2026-10-16: a cancelled booking stayed in the host's iCloud calendar. Deletion went
only through a `calendar-query` REPORT on the UID, and its failure was swallowed without a trace.
GhostCal chose the event's URL itself when it created it (`<calendar>/<uid>.ics`), so that URL is
deleted first, whatever the search does.
"""

from __future__ import annotations

from typing import Any

import pytest

from ghostcal.application.ports.calendar import CalendarCredentials
from ghostcal.infrastructure.calendars import caldav_client
from ghostcal.infrastructure.calendars.dav import DavError

CAL = "https://p141-caldav.icloud.com/123/calendars/home/"
CREDS = CalendarCredentials(server_url="https://caldav.icloud.com", username="u", password="p")


class FakeDav:
    def __init__(self, *, report: str | Exception) -> None:
        self.report = report
        self.deleted: list[str] = []

    async def __aenter__(self) -> FakeDav:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def delete(self, url: str) -> None:
        self.deleted.append(url)

    async def request(self, method: str, url: str, body: str | None, depth: str = "0") -> str:
        if isinstance(self.report, Exception):
            raise self.report
        return self.report


@pytest.fixture
def dav(monkeypatch: pytest.MonkeyPatch) -> Any:
    holder: dict[str, FakeDav] = {}

    def install(fake: FakeDav) -> FakeDav:
        holder["dav"] = fake
        monkeypatch.setattr(caldav_client, "DavSession", lambda *a, **k: fake)
        monkeypatch.setattr(caldav_client, "_guard", lambda url: None)
        return fake

    return install


async def test_known_url_is_deleted_even_when_the_uid_search_fails(dav: Any) -> None:
    fake = dav(FakeDav(report=DavError("HTTP 400")))
    await caldav_client.CaldavCalendarClient().delete_event(CREDS, CAL, "ghostcal-abc")
    assert fake.deleted == [f"{CAL}ghostcal-abc.ics"]


async def test_an_event_stored_under_another_name_is_found_by_uid(dav: Any) -> None:
    other = "/123/calendars/home/ABCDEF.ics"
    multistatus = (
        '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:"><d:response>'
        f"<d:href>{other}</d:href><d:propstat><d:prop><d:getetag>1</d:getetag></d:prop>"
        "<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response></d:multistatus>"
    )
    fake = dav(FakeDav(report=multistatus))
    await caldav_client.CaldavCalendarClient().delete_event(CREDS, CAL, "ghostcal-abc")
    assert fake.deleted[0] == f"{CAL}ghostcal-abc.ics"
    assert fake.deleted[1].endswith("/123/calendars/home/ABCDEF.ics")
