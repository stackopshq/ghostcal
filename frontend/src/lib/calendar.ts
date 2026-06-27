// CalDAV calendar connection API client.

import { authedFetch } from "@/lib/auth";

export type CalendarStatus = {
  connected: boolean;
  server_url: string | null;
  username: string | null;
  calendar_name: string | null;
  status: string | null;
  last_synced_at: string | null;
};

export type CalendarInfo = { name: string; url: string };

export type CalendarCreds = {
  server_url: string;
  username: string;
  password: string;
};

export function getCalendarStatus(): Promise<CalendarStatus> {
  return authedFetch<CalendarStatus>("/v1/me/calendar");
}

export function listCalendars(creds: CalendarCreds): Promise<CalendarInfo[]> {
  return authedFetch<CalendarInfo[]>("/v1/me/calendar/calendars", {
    method: "POST",
    body: JSON.stringify(creds),
  });
}

export function connectCalendar(
  body: CalendarCreds & { calendar_url: string; calendar_name?: string | null },
): Promise<CalendarStatus> {
  return authedFetch<CalendarStatus>("/v1/me/calendar", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function syncCalendar(): Promise<{ synced: number }> {
  return authedFetch<{ synced: number }>("/v1/me/calendar/sync", { method: "POST" });
}

export function disconnectCalendar(): Promise<void> {
  return authedFetch<void>("/v1/me/calendar", { method: "DELETE" });
}
