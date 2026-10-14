"""Meeting-link rule and email (no DB, no real provider)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ghostcal.application.meetings import InvalidMeetingUrl, validate_meeting_url
from ghostcal.application.notifications import send_booking_confirmation, send_meeting_link
from tests.test_notifications import CONF, FakeMailer


@pytest.mark.parametrize(
    "url",
    [
        "https://zoom.us/j/123456789?pwd=abc",
        "https://meet.google.com/abc-defg-hij",
        "  https://teams.microsoft.com/l/meetup-join/x  ",
    ],
)
def test_accepts_https_meeting_links(url: str) -> None:
    assert validate_meeting_url(url) == url.strip()


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://zoom.us/j/1",
        "javascript:alert(1)",
        "zoom.us/j/1",
        "https://",
        "https://zoom.us/j/1 extra",
        "https://zoom.us/" + "a" * 2048,
    ],
)
def test_refuses_anything_but_an_https_url(url: str) -> None:
    with pytest.raises(InvalidMeetingUrl):
        validate_meeting_url(url)


async def test_meeting_link_goes_to_every_recipient_escaped() -> None:
    mailer = FakeMailer()
    url = 'https://zoom.us/j/1?pwd=a&x="><script>'
    await send_meeting_link(
        mailer,
        to=["alice@example.com", "guest@example.com"],
        invitee_timezone="Europe/Zurich",
        event_title="Intro <b>call</b>",
        host_name="Kevin",
        start_at=datetime(2027, 6, 7, 13, 0, tzinfo=UTC),
        meeting_url=url,
        manage_url="https://cal.example.com/manage/tok",
    )
    assert [m.to for m in mailer.sent] == ["alice@example.com", "guest@example.com"]
    html = mailer.sent[0].html
    assert "<script>" not in html and "<b>" not in html
    assert 'href="https://zoom.us/j/1?pwd=a&amp;x=&quot;&gt;&lt;script&gt;"' in html
    assert "https://cal.example.com/manage/tok" in html
    assert mailer.sent[0].subject == "Meeting link: Intro <b>call</b> with Kevin"


async def test_confirmation_offers_reschedule_to_the_invitee_only() -> None:
    mailer = FakeMailer()
    await send_booking_confirmation(mailer, CONF, manage_url="https://cal.example.com/manage/tok")
    by_recipient = {m.to: m.html for m in mailer.sent}
    assert "Reschedule or cancel" in by_recipient[CONF.invitee_email]
    assert "https://cal.example.com/manage/tok" not in by_recipient[CONF.host_email]
