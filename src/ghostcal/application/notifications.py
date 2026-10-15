"""Booking notification emails (confirmation, meeting link, cancellation) with an ICS attachment.

Every message carries French then English (see ``bilingual``).

Pure-ish: takes the ``EmailSender`` port and plain data, builds the content, and sends. Errors
are the caller's concern (sends are best-effort and must not fail the booking).
"""

from __future__ import annotations

import html
from collections.abc import Sequence
from datetime import UTC, datetime

from ghostcal.application import bilingual as bi
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
    "google_meet": ("Google Meet", "Google Meet"),
    "ms_teams": ("Microsoft Teams", "Microsoft Teams"),
    "zoom": ("Zoom", "Zoom"),
    "in_person": ("En personne", "In person"),
    "phone": ("Téléphone", "Phone"),
    "custom": ("Autre", "Custom"),
}


def _location_fr(location_type: str) -> str:
    return _LOCATION_LABELS.get(location_type, (location_type, location_type))[0]


def _location_label(location_type: str) -> str:
    return _LOCATION_LABELS.get(location_type, (location_type, location_type))[1]


def _invitee_label(name: str | None, email: str) -> str:
    """How to refer to the invitee in host-facing copy. The name is zero-knowledge, so for
    booking-page bookings only the email is known server-side."""
    return f"{name} ({email})" if name else email


def _attendee_line(name: str | None, email: str) -> str:
    return f"ATTENDEE;CN={_ics(name)}:mailto:{email}" if name else f"ATTENDEE:mailto:{email}"


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


_BUTTON_STYLE = (
    "display:inline-block;padding:10px 18px;border-radius:999px;background:#21222C;"
    "color:#ffffff;text-decoration:none;font-weight:600"
)


def _button(url: str, label: str) -> str:
    """A link styled as a button, with inline CSS since mail clients drop stylesheets."""
    return f'<p><a href="{_h(url)}" style="{_BUTTON_STYLE}">{_h(label)}</a></p>'


def _manage_block(manage_url: str | None, *, fr: bool) -> str:
    """The invitee's self-service link, as a button: a plain link at the foot of the mail went
    unnoticed by invitees who wanted to move their meeting."""
    if not manage_url:
        return ""
    if fr:
        return f"<p>Besoin de changer ?</p>{_button(manage_url, 'Déplacer ou annuler')}"
    return f"<p>Need to change it?</p>{_button(manage_url, 'Reschedule or cancel')}"


def _join_block(meeting_url: str | None, *, fr: bool) -> str:
    if not meeting_url:
        return ""
    label = "Rejoindre la réunion" if fr else "Join the meeting"
    return (
        f'{_button(meeting_url, label)}<p style="font-size:12px;color:#666">{_h(meeting_url)}</p>'
    )


def _confirmation_html(
    conf: BookingConfirmation,
    *,
    timezone: str,
    counterpart: str,
    manage_url: str | None = None,
) -> str:
    fr = (
        f"<p>Votre rendez-vous est confirmé.</p>"
        f"<p><strong>{_h(conf.event_title)}</strong><br>"
        f"Avec : {_h(counterpart)}<br>"
        f"Quand : {bi.when_fr(conf.start_at, timezone)}<br>"
        f"Où : {_location_fr(conf.location_type)}</p>"
        f"<p>L'invitation pour votre agenda est jointe.</p>"
        f"{_manage_block(manage_url, fr=True)}"
    )
    en = (
        f"<p>Your meeting is confirmed.</p>"
        f"<p><strong>{_h(conf.event_title)}</strong><br>"
        f"With: {_h(counterpart)}<br>"
        f"When: {bi.when_en(conf.start_at, timezone)}<br>"
        f"Where: {_location_label(conf.location_type)}</p>"
        f"<p>The calendar invite is attached.</p>"
        f"{_manage_block(manage_url, fr=False)}"
    )
    return bi.body(fr, en)


async def send_booking_confirmation(
    mailer: EmailSender, conf: BookingConfirmation, *, manage_url: str | None = None
) -> None:
    invite = Attachment("invite.ics", build_ics(conf).encode("utf-8"), "text/calendar")
    title, host = conf.event_title, conf.host_name

    await mailer.send(
        to=conf.invitee_email,
        subject=bi.subject(f"Confirmé : {title} avec {host}", f"Confirmed: {title} with {host}"),
        html=_confirmation_html(
            conf,
            timezone=conf.invitee_timezone,
            counterpart=host,
            manage_url=manage_url,
        ),
        attachments=[invite],
    )
    invitee_label = _invitee_label(conf.invitee_name, conf.invitee_email)
    host_subject = bi.subject(f"Nouvelle réservation : {title}", f"New booking: {title}")
    host_html = _confirmation_html(conf, timezone=conf.host_timezone, counterpart=invitee_label)
    await mailer.send(
        to=conf.host_email, subject=host_subject, html=host_html, attachments=[invite]
    )
    # Co-hosts of a collective meeting get the same host notification.
    for cohost_email in conf.additional_host_emails:
        await mailer.send(
            to=cohost_email, subject=host_subject, html=host_html, attachments=[invite]
        )
    # Additional guests get the same invite (best-effort, like every send here).
    for guest in conf.guest_emails:
        await mailer.send(
            to=guest,
            subject=bi.subject(
                f"Invitation : {title} avec {host}", f"Invitation: {title} with {host}"
            ),
            html=_confirmation_html(conf, timezone=conf.invitee_timezone, counterpart=host),
            attachments=[invite],
        )


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
    lead_fr, lead_en = bi.lead_fr(minutes_before), bi.lead_en(minutes_before)
    fr = (
        f"<p>Petit rappel : votre rendez-vous commence {lead_fr}.</p>"
        f"<p><strong>{_h(event_title)}</strong><br>"
        f"Avec : {_h(host_name)}<br>"
        f"Quand : {bi.when_fr(start_at, invitee_timezone)}<br>"
        f"Où : {_location_fr(location_type)}</p>"
        f"{_manage_block(manage_url, fr=True)}"
    )
    en = (
        f"<p>This is a reminder that your meeting starts {lead_en}.</p>"
        f"<p><strong>{_h(event_title)}</strong><br>"
        f"With: {_h(host_name)}<br>"
        f"When: {bi.when_en(start_at, invitee_timezone)}<br>"
        f"Where: {_location_label(location_type)}</p>"
        f"{_manage_block(manage_url, fr=False)}"
    )
    await mailer.send(
        to=invitee_email,
        subject=bi.subject(
            f"Rappel : {event_title} avec {host_name} ({lead_fr})",
            f"Reminder: {event_title} with {host_name} ({lead_en})",
        ),
        html=bi.body(fr, en),
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
    lead_fr, lead_en = bi.lead_fr(minutes_before), bi.lead_en(minutes_before)
    await mailer.send(
        to=to,
        subject=bi.subject(f"Rappel : un événement {lead_fr}", f"Reminder: an event {lead_en}"),
        html=bi.body(
            f"<p>Vous avez un événement {lead_fr}.</p>"
            f"<p><strong>Quand :</strong> {bi.when_fr(start_at, timezone)}</p>"
            f"<p>Ouvrez GhostCal pour voir les détails : ils sont chiffrés de bout en bout.</p>",
            f"<p>You have a calendar event {lead_en}.</p>"
            f"<p><strong>When:</strong> {bi.when_en(start_at, timezone)}</p>"
            f"<p>Open GhostCal to see the details: they're end-to-end encrypted.</p>",
        ),
    )


async def send_task_reminder(
    mailer: EmailSender,
    *,
    to: str,
    due_at: datetime,
    timezone: str,
    minutes_before: int,
) -> None:
    """Remind the owner of a task that's due soon. Zero-knowledge: the task is never named — the
    server only knows the due time."""
    lead_fr, lead_en = bi.lead_fr(minutes_before), bi.lead_en(minutes_before)
    await mailer.send(
        to=to,
        subject=bi.subject(
            f"Rappel : une tâche à échéance {lead_fr}", f"Reminder: a task due {lead_en}"
        ),
        html=bi.body(
            f"<p>Vous avez une tâche à échéance {lead_fr}.</p>"
            f"<p><strong>Échéance :</strong> {bi.when_fr(due_at, timezone)}</p>"
            f"<p>Ouvrez GhostCal pour la voir : vos tâches sont chiffrées de bout en bout.</p>",
            f"<p>You have a task due {lead_en}.</p>"
            f"<p><strong>Due:</strong> {bi.when_en(due_at, timezone)}</p>"
            f"<p>Open GhostCal to see it: your tasks are end-to-end encrypted.</p>",
        ),
    )


def _invitation_ics(
    *,
    uid: str,
    title: str,
    location: str,
    organizer_name: str,
    start_at: datetime,
    end_at: datetime,
) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//GhostCal//Invitation//EN",
        "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:{uid}@ghostcal",
        f"DTSTAMP:{_ics_dt(start_at)}",
        f"DTSTART:{_ics_dt(start_at)}",
        f"DTEND:{_ics_dt(end_at)}",
        f"SUMMARY:{_ics(title)}",
        *([f"LOCATION:{_ics(location)}"] if location else []),
        f"ORGANIZER;CN={_ics(organizer_name)}:mailto:noreply@ghostcal",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines)


async def send_event_invitation(
    mailer: EmailSender,
    *,
    to: str,
    title: str,
    location: str,
    organizer_name: str,
    start_at: datetime,
    end_at: datetime,
    all_day: bool,
    rsvp_url: str,
) -> None:
    """Invite a guest to a personal event. The cleartext title/location come from the organiser's
    browser and are used only to build this message; the server does not store them. The ICS is
    inlined so the recipient can add it, and an RSVP link records accept/decline/tentative."""
    if all_day:
        when_fr, when_en = bi.date_fr(start_at), bi.date_en(start_at)
    else:
        when_fr, when_en = bi.when_fr(start_at, "UTC"), bi.when_en(start_at, "UTC")
    ics = _invitation_ics(
        uid=rsvp_url.rsplit("/", 1)[-1],
        title=title,
        location=location,
        organizer_name=organizer_name,
        start_at=start_at,
        end_at=end_at,
    )
    where_fr = f"<p><strong>Où :</strong> {_h(location)}</p>" if location else ""
    where_en = f"<p><strong>Where:</strong> {_h(location)}</p>" if location else ""
    fr = (
        f"<p>{_h(organizer_name)} vous invite à <strong>{_h(title)}</strong>.</p>"
        f"<p><strong>Quand :</strong> {_h(when_fr)}</p>"
        f"{where_fr}"
        f'<p>Répondre : <a href="{rsvp_url}">accepter, refuser ou peut-être</a>.</p>'
    )
    en = (
        f"<p>{_h(organizer_name)} invited you to <strong>{_h(title)}</strong>.</p>"
        f"<p><strong>When:</strong> {_h(when_en)}</p>"
        f"{where_en}"
        f'<p>Respond: <a href="{rsvp_url}">accept, decline or maybe</a>.</p>'
    )
    await mailer.send(
        to=to,
        subject=bi.subject(f"Invitation : {_h(title)}", f"Invitation: {_h(title)}"),
        html=bi.body(fr, en) + f"<hr><pre>{_h(ics)}</pre>",
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
    fr = (
        f"<p>Bonjour {_h(attendee_name)}, l'horaire de "
        f"<strong>{_h(poll_title)}</strong> est fixé.</p>"
        f"<p>Quand : {bi.when_fr(start_at, timezone)}<br>"
        f"Organisé par : {_h(owner_name)}<br>"
        f"Où : {_location_fr(location_type)}</p>"
        f"<p>L'invitation pour votre agenda est jointe.</p>"
    )
    en = (
        f"<p>Hi {_h(attendee_name)}, the time for "
        f"<strong>{_h(poll_title)}</strong> has been set.</p>"
        f"<p>When: {bi.when_en(start_at, timezone)}<br>"
        f"Host: {_h(owner_name)}<br>"
        f"Where: {_location_label(location_type)}</p>"
        f"<p>The calendar invite is attached.</p>"
    )
    await mailer.send(
        to=to_email,
        subject=bi.subject(f"Horaire confirmé : {poll_title}", f"Time confirmed: {poll_title}"),
        html=bi.body(fr, en),
        attachments=[invite],
    )


async def send_meeting_link(
    mailer: EmailSender,
    *,
    to: Sequence[str],
    invitee_timezone: str,
    event_title: str,
    host_name: str,
    start_at: datetime,
    meeting_url: str,
    manage_url: str | None = None,
) -> None:
    """Send the video-call link the host set on a booking to the invitee and their guests."""
    fr = (
        f"<p>{_h(host_name)} vous envoie le lien pour rejoindre votre rendez-vous.</p>"
        f"<p><strong>{_h(event_title)}</strong><br>"
        f"Quand : {bi.when_fr(start_at, invitee_timezone)}</p>"
        f"{_join_block(meeting_url, fr=True)}"
        f"{_manage_block(manage_url, fr=True)}"
    )
    en = (
        f"<p>{_h(host_name)} shared the link to join your meeting.</p>"
        f"<p><strong>{_h(event_title)}</strong><br>"
        f"When: {bi.when_en(start_at, invitee_timezone)}</p>"
        f"{_join_block(meeting_url, fr=False)}"
        f"{_manage_block(manage_url, fr=False)}"
    )
    for recipient in to:
        await mailer.send(
            to=recipient,
            subject=bi.subject(
                f"Lien de la réunion : {event_title} avec {host_name}",
                f"Meeting link: {event_title} with {host_name}",
            ),
            html=bi.body(fr, en),
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
    with_fr = f" avec {host_name}" if host_name else ""
    with_en = f" with {host_name}" if host_name else ""
    await mailer.send(
        to=invitee_email,
        subject=bi.subject(
            f"Annulé : {event_title}{with_fr}", f"Cancelled: {event_title}{with_en}"
        ),
        html=bi.body(
            f"<p>Votre rendez-vous a été annulé.</p>"
            f"<p><strong>{_h(event_title)}</strong><br>"
            f"Quand : {bi.when_fr(start_at, invitee_timezone)}</p>"
            f"<p>Vous pouvez réserver un autre créneau si besoin.</p>",
            f"<p>Your meeting has been cancelled.</p>"
            f"<p><strong>{_h(event_title)}</strong><br>"
            f"When: {bi.when_en(start_at, invitee_timezone)}</p>"
            f"<p>You can book another time if you still need to meet.</p>",
        ),
    )
