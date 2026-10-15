"""Video-meeting rooms generated at booking time, for locations that need no account.

kMeet (Infomaniak, built on Jitsi) opens a room for any unique path on its instance: Infomaniak's
API documentation for `POST /1/kmeet/rooms` states that "if you just want to create a room you
don't need any API calls" -- the URL is the instance plus a unique identifier. Nothing is sent to
Infomaniak at booking time, and nothing has to be deleted when the booking is cancelled.

The identifier is the room's only protection: whoever knows the URL can join. 128 random bits,
hex-encoded so it survives every client that lower-cases or re-encodes a path.
"""

from __future__ import annotations

import secrets

KMEET_HOST = "kmeet.infomaniak.com"

# Locations for which GhostCal creates the room itself when the booking is made.
GENERATED_ROOM_LOCATIONS: frozenset[str] = frozenset({"kmeet"})


def new_room_url(location_type: str) -> str | None:
    """A fresh meeting URL for ``location_type``, or None when the host provides the link."""
    if location_type == "kmeet":
        return f"https://{KMEET_HOST}/{secrets.token_hex(16)}"
    return None
