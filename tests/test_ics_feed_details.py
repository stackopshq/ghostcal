"""A subscribed feed keeps the room and the notes of each event, not only its title.

Reported 2026-10-18: a university timetable showed course codes and nothing else; the room and the
teacher are in LOCATION and DESCRIPTION, which the parser dropped.
"""

from __future__ import annotations

from ghostcal.infrastructure.calendars.ics_feed import parse_feed_body

FEED = b"""BEGIN:VCALENDAR\r
VERSION:2.0\r
PRODID:-//Univ//Timetable//FR\r
BEGIN:VEVENT\r
UID:course-1@univ.test\r
DTSTART:20261019T111500Z\r
DTEND:20261019T131500Z\r
SUMMARY:METH101D1_SVT Gr5\r
LOCATION:Amphi Pasteur\r
DESCRIPTION:Enseignant : Mme Martin\\nGroupe 5\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:course-2@univ.test\r
DTSTART:20261020T111500Z\r
DTEND:20261020T131500Z\r
SUMMARY:GEOL104D1_ST Gr5\r
LOCATION:   \r
END:VEVENT\r
END:VCALENDAR\r
"""


def test_location_and_description_are_kept() -> None:
    first, second = parse_feed_body(FEED)
    assert first.summary == "METH101D1_SVT Gr5"
    assert first.location == "Amphi Pasteur"
    assert first.description == "Enseignant : Mme Martin\nGroupe 5"
    # Blank or absent properties are None, not an empty string to display.
    assert second.location is None
    assert second.description is None


def test_details_are_bounded() -> None:
    body = FEED.replace(b"Amphi Pasteur", b"x" * 2000)
    first, _ = parse_feed_body(body)
    assert first.location is not None and len(first.location) == 500
