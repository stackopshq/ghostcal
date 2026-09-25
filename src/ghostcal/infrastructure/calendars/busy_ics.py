"""Serialise merged busy blocks as an iCalendar feed a calendar app can subscribe to.

The *data* is already decided elsewhere: :func:`ghostcal.application.scheduling.busy_for`
says when someone is occupied, and ``merge`` flattens the result. This module only
chooses how those intervals are written down. It computes nothing, so it cannot
disagree with the JSON view of the same link — which is the whole reason it takes
blocks as an argument rather than a user id.

WHY A SUBSCRIPTION IS THE RIGHT SHAPE HERE
------------------------------------------
A subscribed calendar carries ``VEVENT`` and drops ``VTODO``. That limitation sinks a
task feed; it is irrelevant to this one, because busy time *is* a set of events. So the
plain, boring mechanism works: paste the URL into any calendar client and it refreshes
itself.

WHAT LEAVES, AND WHAT CANNOT
----------------------------
Every event carries a start, an end, and the word "Occupé". There is no field for a
title here, the same way :class:`BusyBlockOut` has none — a shape that cannot express a
client name cannot leak one by accident later.

Three details are load-bearing rather than decorative:

* **The UID is opaque and derived, never an internal identifier.** A UID built from an
  event's real id would let a subscriber count how many meetings hide inside one merged
  block, and watch which of them survive from one refresh to the next. It is an HMAC
  keyed on the link, so two different links publishing the same hour do not even agree
  with each other.

* **The UID is nevertheless STABLE for the same interval.** A UID that changed on every
  poll would make clients delete and re-add every event, which on a phone means a
  notification storm for time that never moved.

* **Nothing reads the clock.** ``DTSTAMP`` comes from the interval itself. Were it
  ``now``, the bytes would differ on every request, every ``ETag`` would change, and
  every subscriber would re-download the whole calendar every fifteen minutes forever.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Iterable
from datetime import UTC, datetime

#: What every block is called. Fixed, and deliberately not the owner's name: repeating
#: it on each event would republish a person's identity dozens of times inside a file
#: they only meant to say "I am busy" with.
BUSY_SUMMARY = "Occupé"

#: RFC 5545 §3.1: lines are folded at 75 octets. A folded line continues with a single
#: leading space. Folding on OCTETS rather than characters matters — accented French
#: text is two bytes per character, and folding mid-sequence produces a file some
#: clients refuse outright.
_FOLD_OCTETS = 75


def _fold(line: str) -> str:
    raw = line.encode("utf-8")
    if len(raw) <= _FOLD_OCTETS:
        return line
    chunks: list[str] = []
    start = 0
    while start < len(raw):
        end = min(start + (_FOLD_OCTETS if not chunks else _FOLD_OCTETS - 1), len(raw))
        # Never split a UTF-8 sequence: back off until the next byte starts a character.
        while end < len(raw) and (raw[end] & 0xC0) == 0x80:
            end -= 1
        chunks.append(raw[start:end].decode("utf-8"))
        start = end
    return "\r\n ".join(chunks)


def _escape(value: str) -> str:
    """RFC 5545 §3.3.11. Backslash first, or it would escape the escapes."""
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _stamp(moment: datetime) -> str:
    """UTC, basic format, with the trailing Z that says so.

    Converted rather than assumed: ``busy_for`` works in UTC today, and a value that
    arrived in another zone would otherwise be stamped ``Z`` while carrying local
    wall-clock time — an hour of someone's day silently displaced.
    """
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _uid(secret: bytes, start: datetime, end: datetime) -> str:
    digest = hmac.new(secret, f"{start.isoformat()}/{end.isoformat()}".encode(), hashlib.sha256)
    return f"{digest.hexdigest()[:32]}@ghostcal"


def render_busy_calendar(
    *,
    calendar_name: str,
    blocks: Iterable[tuple[datetime, datetime]],
    uid_secret: bytes,
) -> str:
    """The feed, as text. ``uid_secret`` scopes the opaque UIDs to one link.

    Blocks are expected already merged: this function publishes exactly what it is
    given, so handing it unmerged intervals would republish the density that merging
    exists to hide.
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//StackOps//GhostCal Free-Busy//FR",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_escape(calendar_name)}",
        # A quarter of an hour is a hint, not a rule — clients honour it loosely. It is
        # here so a polite client does not poll every minute for data that changes when
        # a human moves a meeting.
        "REFRESH-INTERVAL;VALUE=DURATION:PT15M",
        "X-PUBLISHED-TTL:PT15M",
    ]
    for start, end in blocks:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{_uid(uid_secret, start, end)}",
            f"DTSTAMP:{_stamp(start)}",
            f"DTSTART:{_stamp(start)}",
            f"DTEND:{_stamp(end)}",
            f"SUMMARY:{_escape(BUSY_SUMMARY)}",
            # OPAQUE means "this time is taken" — the flag a colleague's scheduling
            # assistant actually reads. PRIVATE asks clients not to re-share the entry;
            # it is a request, not a control, and it is not what protects the content.
            # What protects the content is that there is none.
            "TRANSP:OPAQUE",
            "CLASS:PRIVATE",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
