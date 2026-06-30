"""Booking notification emails (confirmation, cancellation) with an iCalendar attachment.

Pure-ish: takes the ``EmailSender`` port and plain data, builds the content, and sends. Errors
are the caller's concern (sends are best-effort and must not fail the booking).
"""

from __future__ import annotations

import html
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from ghostcal.application.ports.email import Attachment, EmailSender
from ghostcal.application.scheduling import BookingConfirmation


def _h(value: str | None) -> str:
    """HTML-escape a user-controlled value before interpolating into an email body (anti-XSS)."""
    return html.escape(value or "")


def _ics(value: str | None) -> str:
    """Escape a value for an iCalendar text property per RFC 5545 (and strip CR/LF to block
    property injection)."""
    return (
        (value or "")
        .replace("\\", "\\\\")
        .replace("\r\n", " ")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


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


def _invitee_label(name: str | None, email: str) -> str:
    """How to refer to the invitee in host-facing copy. The name is zero-knowledge, so for
    booking-page bookings only the email is known server-side."""
    return f"{name} ({email})" if name else email


def _attendee_line(name: str | None, email: str) -> str:
    return f"ATTENDEE;CN={_ics(name)}:mailto:{email}" if name else f"ATTENDEE:mailto:{email}"


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
        f"SUMMARY:{_ics(conf.event_title)} with {_ics(conf.host_name)}",
        f"DESCRIPTION:{_ics(conf.event_title)} ({_location_label(conf.location_type)})",
        f"LOCATION:{_location_label(conf.location_type)}",
        f"ORGANIZER;CN={_ics(conf.host_name)}:mailto:{conf.host_email}",
        _attendee_line(conf.invitee_name, conf.invitee_email),
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
        f"<p><strong>{_h(conf.event_title)}</strong><br>"
        f"With: {_h(counterpart)}<br>"
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
    invitee_label = _invitee_label(conf.invitee_name, conf.invitee_email)
    await mailer.send(
        to=conf.host_email,
        subject=f"New booking: {conf.event_title}",
        html=_confirmation_html(
            conf,
            when=_human(conf.start_at, conf.host_timezone),
            counterpart=invitee_label,
        ),
        attachments=[invite],
    )
    # Co-hosts of a collective meeting get the same host notification.
    for cohost_email in conf.additional_host_emails:
        await mailer.send(
            to=cohost_email,
            subject=f"New booking: {conf.event_title}",
            html=_confirmation_html(
                conf,
                when=_human(conf.start_at, conf.host_timezone),
                counterpart=invitee_label,
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
            f"<p><strong>{_h(event_title)}</strong><br>"
            f"With: {_h(host_name)}<br>"
            f"When: {when}<br>"
            f"Where: {_location_label(location_type)}</p>"
            f"{manage}"
        ),
    )


async def send_event_reminder(
    mailer: EmailSender,
    *,
    to: str,
    start_at: datetime,
    timezone: str,
    minutes_before: int,
) -> None:
    """Remind the owner of an upcoming calendar event. Zero-knowledge: the event is never named —
    the server only knows the time."""
    when = _human(start_at, timezone)
    lead = _lead_label(minutes_before)
    await mailer.send(
        to=to,
        subject=f"Reminder: an event {lead}",
        html=(
            f"<p>You have a calendar event {lead}.</p>"
            f"<p><strong>When:</strong> {when}</p>"
            f"<p>Open GhostCal to see the details — they're end-to-end encrypted.</p>"
        ),
    )


def _poll_ics(*, title: str, organizer: str, start_at: datetime, end_at: datetime) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//GhostCal//Poll//EN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:poll-{_ics_dt(start_at)}-{_ics(organizer)}@ghostcal",
        f"DTSTAMP:{_ics_dt(start_at)}",
        f"DTSTART:{_ics_dt(start_at)}",
        f"DTEND:{_ics_dt(end_at)}",
        f"SUMMARY:{_ics(title)}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"


async def send_poll_result(
    mailer: EmailSender,
    *,
    to_email: str,
    attendee_name: str,
    poll_title: str,
    owner_name: str,
    start_at: datetime,
    end_at: datetime,
    location_type: str,
    timezone: str = "UTC",
) -> None:
    invite = Attachment(
        "invite.ics",
        _poll_ics(
            title=poll_title, organizer=owner_name, start_at=start_at, end_at=end_at
        ).encode(),
        "text/calendar",
    )
    await mailer.send(
        to=to_email,
        subject=f"Time confirmed: {poll_title}",
        html=(
            f"<p>Hi {_h(attendee_name)}, the time for "
            f"<strong>{_h(poll_title)}</strong> has been set.</p>"
            f"<p>When: {_human(start_at, timezone)}<br>"
            f"Host: {_h(owner_name)}<br>"
            f"Where: {_location_label(location_type)}</p>"
            f"<p>The calendar invite is attached.</p>"
        ),
        attachments=[invite],
    )


async def send_booking_cancellation(
    mailer: EmailSender,
    *,
    invitee_email: str,
    invitee_timezone: str,
    event_title: str,
    host_name: str | None,
    start_at: datetime,
) -> None:
    when = _human(start_at, invitee_timezone)
    suffix = f" with {host_name}" if host_name else ""
    await mailer.send(
        to=invitee_email,
        subject=f"Cancelled: {event_title}{suffix}",
        html=(
            f"<p>Your meeting has been cancelled.</p>"
            f"<p><strong>{_h(event_title)}</strong><br>When: {when}</p>"
            f"<p>You can book another time if you still need to meet.</p>"
        ),
    )
