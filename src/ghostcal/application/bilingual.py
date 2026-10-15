"""Every email in both languages: French first, then English.

The recipient's language is unknown to the server for most emails (an invitee has no account),
and storing one per address just to pick a template was rejected (2026-10-15): one message
carrying both is correct for every reader and stores nothing.

Dates are spelled from fixed tables, not ``strftime``: ``%A``/``%B`` follow the process locale,
which is whatever the container happens to ship.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

_FR_DAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
_FR_MONTHS = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)  # fmt: skip
_EN_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_EN_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)  # fmt: skip

_SEPARATOR = '<hr style="border:none;border-top:1px solid #dddddd;margin:28px 0">'
_NOTE_STYLE = "font-size:12px;color:#666666"


def subject(fr: str, en: str) -> str:
    return f"{fr} / {en}"


def body(fr: str, en: str) -> str:
    """Both versions, each tagged with its language so screen readers switch voice."""
    return (
        f'<div lang="fr"><p style="{_NOTE_STYLE}">English version below.</p>{fr}</div>'
        f'{_SEPARATOR}<div lang="en">{en}</div>'
    )


def date_fr(dt: datetime) -> str:
    return f"{_FR_DAYS[dt.weekday()]} {dt.day} {_FR_MONTHS[dt.month - 1]} {dt.year}"


def date_en(dt: datetime) -> str:
    return f"{_EN_DAYS[dt.weekday()]}, {dt.day:02d} {_EN_MONTHS[dt.month - 1]} {dt.year}"


def when_fr(dt: datetime, timezone: str) -> str:
    local = dt.astimezone(ZoneInfo(timezone))
    return f"{date_fr(local)} à {local:%H:%M} ({timezone})"


def when_en(dt: datetime, timezone: str) -> str:
    local = dt.astimezone(ZoneInfo(timezone))
    return f"{date_en(local)} at {local:%H:%M} ({timezone})"


def lead_fr(minutes_before: int) -> str:
    if minutes_before % 1440 == 0:
        days = minutes_before // 1440
        return "demain" if days == 1 else f"dans {days} jours"
    if minutes_before % 60 == 0:
        hours = minutes_before // 60
        return "dans 1 heure" if hours == 1 else f"dans {hours} heures"
    return f"dans {minutes_before} minutes"


def lead_en(minutes_before: int) -> str:
    if minutes_before % 1440 == 0:
        days = minutes_before // 1440
        return "tomorrow" if days == 1 else f"in {days} days"
    if minutes_before % 60 == 0:
        hours = minutes_before // 60
        return "in 1 hour" if hours == 1 else f"in {hours} hours"
    return f"in {minutes_before} minutes"
