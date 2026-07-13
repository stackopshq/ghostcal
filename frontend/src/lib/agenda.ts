// Calendar (zero-knowledge personal calendar) API client. Event content is sealed client-side; the
// server only ever sees ciphertext and cleartext scheduling fields. See ADR-0004.

import { authedFetch } from "@/lib/auth";

export type CalendarRec = {
  id: string;
  name: string;
  color: string;
  is_default: boolean;
  is_shared: boolean;
  owner_name: string | null;
  /** Whether the viewer may write to it. Always true for a calendar they own. */
  can_edit: boolean;
};

export type Share = {
  user_id: string;
  name: string;
  /** A read-write share: they may add to, change and remove from the calendar, not merely read it. */
  can_edit: boolean;
};

export type AgendaItem = {
  source: "event" | "booking" | "external" | "subscription";
  start: string;
  end: string;
  all_day: boolean;
  calendar_id: string | null;
  event_id: string | null;
  content: string | null; // sealed blob (events)
  title: string | null; // cleartext label (bookings/external)
  read_only: boolean;
  reminder_minutes: number | null; // minutes before start to alert (events only)
};

export type EventInput = {
  calendar_id: string;
  start_at: string;
  end_at: string;
  timezone: string;
  all_day?: boolean;
  rrule?: string | null;
  exdates?: string[];
  content?: string | null;
  reminder_minutes?: number | null;
};

export type EventDetail = {
  id: string;
  calendar_id: string;
  start_at: string;
  end_at: string;
  timezone: string;
  all_day: boolean;
  rrule: string | null;
  exdates: string[];
  content: string | null;
  reminder_minutes: number | null;
};

export function listCalendars(): Promise<CalendarRec[]> {
  return authedFetch<CalendarRec[]>("/v1/me/calendars");
}

export function createCalendar(
  name: string,
  color: string,
): Promise<CalendarRec> {
  return authedFetch<CalendarRec>("/v1/me/calendars", {
    method: "POST",
    body: JSON.stringify({ name, color }),
  });
}

export function getAgenda(from: string, to: string): Promise<AgendaItem[]> {
  const qs = new URLSearchParams({ from, to });
  return authedFetch<AgendaItem[]>(`/v1/me/calendar/agenda?${qs}`);
}

export function createEvent(body: EventInput): Promise<{ id: string }> {
  return authedFetch<{ id: string }>("/v1/me/calendar/events", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getEvent(id: string): Promise<EventDetail> {
  return authedFetch<EventDetail>(`/v1/me/calendar/events/${id}`);
}

export function updateEvent(id: string, body: EventInput): Promise<void> {
  return authedFetch<void>(`/v1/me/calendar/events/${id}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function deleteEvent(id: string): Promise<void> {
  return authedFetch<void>(`/v1/me/calendar/events/${id}`, {
    method: "DELETE",
  });
}

export function listShares(calendarId: string): Promise<Share[]> {
  return authedFetch<Share[]>(`/v1/me/calendars/${calendarId}/shares`);
}

/**
 * Share a calendar with a colleague, read-only or read-write.
 *
 * Re-posting an existing share is how the owner changes their mind about which — the server upserts,
 * so a downgrade takes effect rather than silently doing nothing.
 *
 * Zero-knowledge holds either way: both are members of the same org and already hold the org key, so
 * an editor unseals and re-seals exactly as the owner does. The server sees ciphertext throughout.
 */
export function shareCalendar(
  calendarId: string,
  userId: string,
  canEdit = false,
): Promise<void> {
  return authedFetch<void>(`/v1/me/calendars/${calendarId}/shares`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId, can_edit: canEdit }),
  });
}

export function unshareCalendar(
  calendarId: string,
  userId: string,
): Promise<void> {
  return authedFetch<void>(`/v1/me/calendars/${calendarId}/shares/${userId}`, {
    method: "DELETE",
  });
}

// --- Event attendees (personal-calendar invitations) -----------------------------------------

export type Attendee = {
  id: string;
  email: string;
  name: string | null;
  status: "needs_action" | "accepted" | "declined" | "tentative";
};

export function listAttendees(eventId: string): Promise<Attendee[]> {
  return authedFetch<Attendee[]>(`/v1/me/calendar/events/${eventId}/attendees`);
}

export function addAttendee(
  eventId: string,
  email: string,
  name: string | null,
): Promise<{ id: string; email: string; token: string }> {
  return authedFetch(`/v1/me/calendar/events/${eventId}/attendees`, {
    method: "POST",
    body: JSON.stringify({ email, name }),
  });
}

export function removeAttendee(
  eventId: string,
  attendeeId: string,
): Promise<void> {
  return authedFetch<void>(
    `/v1/me/calendar/events/${eventId}/attendees/${attendeeId}`,
    {
      method: "DELETE",
    },
  );
}

// Send the invitation email. Cleartext title/location come from the browser (decrypted here) and
// are used only to build the ICS email — the server never stores them.
export function sendInvitation(
  eventId: string,
  body: {
    email: string;
    token: string;
    title: string;
    location: string;
    organizer_name: string;
    start_at: string;
    end_at: string;
    all_day: boolean;
  },
): Promise<{ status: string }> {
  return authedFetch(`/v1/me/calendar/events/${eventId}/invite`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// --- Public RSVP (no auth) -------------------------------------------------------------------

export type InvitePreview = {
  start_at: string;
  end_at: string;
  timezone: string;
  all_day: boolean;
  status: string;
};

export async function getEventInvite(
  token: string,
): Promise<InvitePreview | null> {
  const res = await fetch(`/api/v1/invitations/event/${token}`, {
    cache: "no-store",
  });
  if (!res.ok) return null;
  return (await res.json()) as InvitePreview;
}

export async function respondEventInvite(
  token: string,
  status: string,
): Promise<boolean> {
  const res = await fetch(`/api/v1/invitations/event/${token}/respond`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  return res.ok;
}
