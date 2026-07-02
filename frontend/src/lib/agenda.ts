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
};

export type Share = { user_id: string; name: string };

export type AgendaItem = {
  source: "event" | "booking" | "external";
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
  return authedFetch<void>(`/v1/me/calendar/events/${id}`, { method: "DELETE" });
}

export function listShares(calendarId: string): Promise<Share[]> {
  return authedFetch<Share[]>(`/v1/me/calendars/${calendarId}/shares`);
}

export function shareCalendar(calendarId: string, userId: string): Promise<void> {
  return authedFetch<void>(`/v1/me/calendars/${calendarId}/shares`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}

export function unshareCalendar(calendarId: string, userId: string): Promise<void> {
  return authedFetch<void>(`/v1/me/calendars/${calendarId}/shares/${userId}`, { method: "DELETE" });
}
