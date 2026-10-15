"""Every email carries French then English, with dates that do not depend on the locale."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ghostcal.application import bilingual as bi
from ghostcal.application.notifications import send_booking_cancellation, send_booking_reminder


class _Mailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def send(self, **kwargs: object) -> None:
        self.sent.append(kwargs)


START = datetime(2026, 10, 20, 13, 30, tzinfo=UTC)


def test_dates_in_both_languages() -> None:
    assert bi.when_fr(START, "Europe/Paris") == "mardi 20 octobre 2026 à 15:30 (Europe/Paris)"
    assert bi.when_en(START, "Europe/Paris") == "Tuesday, 20 October 2026 at 15:30 (Europe/Paris)"


@pytest.mark.parametrize(
    ("minutes", "fr", "en"),
    [
        (1440, "demain", "tomorrow"),
        (120, "dans 2 heures", "in 2 hours"),
        (15, "dans 15 minutes", "in 15 minutes"),
    ],
)
def test_lead_labels(minutes: int, fr: str, en: str) -> None:
    assert (bi.lead_fr(minutes), bi.lead_en(minutes)) == (fr, en)


async def test_reminder_is_french_then_english() -> None:
    mailer = _Mailer()
    await send_booking_reminder(
        mailer,  # type: ignore[arg-type]
        invitee_email="a@example.com",
        invitee_timezone="Europe/Paris",
        event_title="Découverte",
        host_name="Kevin",
        location_type="in_person",
        start_at=START,
        minutes_before=1440,
        manage_url="https://cal.example.com/manage/t",
    )
    sent = mailer.sent[0]
    assert sent["subject"] == (
        "Rappel : Découverte avec Kevin (demain) / Reminder: Découverte with Kevin (tomorrow)"
    )
    html = str(sent["html"])
    assert html.index('lang="fr"') < html.index('lang="en"')
    assert "En personne" in html and "In person" in html
    assert "Déplacer ou annuler" in html and "Reschedule or cancel" in html


async def test_cancellation_without_host() -> None:
    mailer = _Mailer()
    await send_booking_cancellation(
        mailer,  # type: ignore[arg-type]
        invitee_email="a@example.com",
        invitee_timezone="UTC",
        event_title="Point",
        host_name=None,
        start_at=START,
    )
    assert mailer.sent[0]["subject"] == "Annulé : Point / Cancelled: Point"
