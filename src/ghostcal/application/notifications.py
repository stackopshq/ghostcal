"""Booking notification emails (confirmation, cancellation) with an iCalendar attachment.

Pure-ish: takes the ``EmailSender`` port and plain data, builds the content, and sends. Errors
are the caller's concern (sends are best-effort and must not fail the booking).
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from ghostcal.application.ports.email import Attachment, EmailSender
from ghostcal.application.scheduling import BookingConfirmation

_LOCATION_LABELS = {
    "google_meet": "Google Meet",
    "ms_teams": "Microsoft Teams",
    "zoom": "Zoom",
    "in_person": "In person",
    "phone": "Phone",
    "custom": "Custom",
}


def _location_label(location_type: str) -> str:
    return _LOCATION_LABELS.get(location_type, location_type)


def _human(dt: datetime, timezone: str) -> str:
    local = dt.astimezone(ZoneInfo(timezone))
    return f"{local.strftime('%A, %d %B %Y at %H:%M')} ({timezone})"


def _ics_dt(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def build_ics(conf: BookingConfirmation) -> str:
    """A minimal, valid VEVENT for the booking."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//GhostCal//Booking//EN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{conf.booking_id}@ghostcal",
        f"DTSTAMP:{_ics_dt(conf.start_at)}",
        f"DTSTART:{_ics_dt(conf.start_at)}",
        f"DTEND:{_ics_dt(conf.end_at)}",
        f"SUMMARY:{conf.event_title} with {conf.host_name}",
        f"DESCRIPTION:{conf.event_title} ({_location_label(conf.location_type)})",
        f"LOCATION:{_location_label(conf.location_type)}",
        f"ORGANIZER;CN={conf.host_name}:mailto:{conf.host_email}",
        f"ATTENDEE;CN={conf.invitee_name}:mailto:{conf.invitee_email}",
        *(f"ATTENDEE:mailto:{guest}" for guest in conf.guest_emails),
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"


def _confirmation_html(
    conf: BookingConfirmation, *, when: str, counterpart: str, manage_url: str | None = None
) -> str:
    manage = (
        f'<p>Need to change it? <a href="{manage_url}">Reschedule or cancel</a>.</p>'
        if manage_url
        else ""
    )
    return (
        f"<p>Your meeting is confirmed.</p>"
        f"<p><strong>{conf.event_title}</strong><br>"
        f"With: {counterpart}<br>"
        f"When: {when}<br>"
        f"Where: {_location_label(conf.location_type)}</p>"
        f"<p>The calendar invite is attached.</p>"
        f"{manage}"
    )


async def send_booking_confirmation(
    mailer: EmailSender, conf: BookingConfirmation, *, manage_url: str | None = None
) -> None:
    invite = Attachment("invite.ics", build_ics(conf).encode("utf-8"), "text/calendar")

    await mailer.send(
        to=conf.invitee_email,
        subject=f"Confirmed: {conf.event_title} with {conf.host_name}",
        html=_confirmation_html(
            conf,
            when=_human(conf.start_at, conf.invitee_timezone),
            counterpart=conf.host_name,
            manage_url=manage_url,
        ),
        attachments=[invite],
    )
    await mailer.send(
        to=conf.host_email,
        subject=f"New booking: {conf.event_title} with {conf.invitee_name}",
        html=_confirmation_html(
            conf,
            when=_human(conf.start_at, conf.host_timezone),
            counterpart=f"{conf.invitee_name} ({conf.invitee_email})",
        ),
        attachments=[invite],
    )
    # Co-hosts of a collective meeting get the same host notification.
    for cohost_email in conf.additional_host_emails:
        await mailer.send(
            to=cohost_email,
            subject=f"New booking: {conf.event_title} with {conf.invitee_name}",
            html=_confirmation_html(
                conf,
                when=_human(conf.start_at, conf.host_timezone),
                counterpart=f"{conf.invitee_name} ({conf.invitee_email})",
            ),
            attachments=[invite],
        )
    # Additional guests get the same invite (best-effort, like every send here).
    for guest in conf.guest_emails:
        await mailer.send(
            to=guest,
            subject=f"Invitation: {conf.event_title} with {conf.host_name}",
            html=_confirmation_html(
                conf,
                when=_human(conf.start_at, conf.invitee_timezone),
                counterpart=conf.host_name,
            ),
            attachments=[invite],
        )


def _lead_label(minutes_before: int) -> str:
    if minutes_before % 1440 == 0:
        days = minutes_before // 1440
        return "tomorrow" if days == 1 else f"in {days} days"
    if minutes_before % 60 == 0:
        hours = minutes_before // 60
        return "in 1 hour" if hours == 1 else f"in {hours} hours"
    return f"in {minutes_before} minutes"


async def send_booking_reminder(
    mailer: EmailSender,
    *,
    invitee_email: str,
    invitee_timezone: str,
    event_title: str,
    host_name: str,
    location_type: str,
    start_at: datetime,
    minutes_before: int,
    manage_url: str | None = None,
) -> None:
    when = _human(start_at, invitee_timezone)
    lead = _lead_label(minutes_before)
    manage = (
        f'<p>Need to change it? <a href="{manage_url}">Reschedule or cancel</a>.</p>'
        if manage_url
        else ""
    )
    await mailer.send(
        to=invitee_email,
        subject=f"Reminder: {event_title} with {host_name} ({lead})",
        html=(
            f"<p>This is a reminder that your meeting starts {lead}.</p>"
            f"<p><strong>{event_title}</strong><br>"
            f"With: {host_name}<br>"
            f"When: {when}<br>"
            f"Where: {_location_label(location_type)}</p>"
            f"{manage}"
        ),
    )


async def send_booking_cancellation(
    mailer: EmailSender,
    *,
    invitee_email: str,
    invitee_timezone: str,
    event_title: str,
    host_name: str,
    start_at: datetime,
) -> None:
    when = _human(start_at, invitee_timezone)
    await mailer.send(
        to=invitee_email,
        subject=f"Cancelled: {event_title} with {host_name}",
        html=(
            f"<p>Your meeting has been cancelled.</p>"
            f"<p><strong>{event_title}</strong><br>When: {when}</p>"
            f"<p>You can book another time if you still need to meet.</p>"
        ),
    )
