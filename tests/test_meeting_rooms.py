"""Rooms generated at booking time (no account, no provider call)."""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from ghostcal.application.event_types import LOCATION_TYPES
from ghostcal.application.meeting_rooms import GENERATED_ROOM_LOCATIONS, new_room_url
from ghostcal.presentation.schemas import MeetingLinkIn


def test_kmeet_room_is_a_unique_unguessable_url() -> None:
    first, second = new_room_url("kmeet"), new_room_url("kmeet")
    assert first is not None and second is not None
    assert re.fullmatch(r"https://kmeet\.infomaniak\.com/[0-9a-f]{32}", first)
    assert first != second


def test_locations_without_a_generator_get_no_url() -> None:
    for location in ("google_meet", "zoom", "ms_teams", "in_person", "phone", "custom"):
        assert new_room_url(location) is None


def test_every_generated_location_is_selectable() -> None:
    assert GENERATED_ROOM_LOCATIONS.issubset(LOCATION_TYPES)


def test_meeting_link_payload_takes_a_url_or_a_provider_not_both() -> None:
    assert MeetingLinkIn(url="https://zoom.us/j/1").provider is None
    assert MeetingLinkIn(provider="kmeet").url is None
    for bad in ({}, {"url": "https://zoom.us/j/1", "provider": "kmeet"}, {"provider": "zoom"}):
        with pytest.raises(ValidationError):
            MeetingLinkIn(**bad)
