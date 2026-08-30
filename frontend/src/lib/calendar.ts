// Connected external (CalDAV) calendars.
//
// Several per person — work, personal, family — which is ordinary for a calendar client. Two things
// follow, and the UI has to make both visible rather than leave them implicit:
//
// - bookings are written back to exactly ONE of them (`mirror_bookings`). Mirroring onto all would
//   duplicate every meeting, and the host would find out from their own phone, not from us.
// - each one has its own colour, so it is its own overlay in the calendar instead of three accounts
//   collapsing into a single anonymous "External" chip.

import { authedFetch } from "@/lib/auth";

export type Connection = {
  id: string;
  server_url: string;
  username: string;
  calendar_name: string | null;
  color: string;
  /** The one calendar bookings are mirrored onto. Exactly one of the user's connections has it. */
  mirror_bookings: boolean;
  status: string;
  last_synced_at: string | null;
};

export type CalendarInfo = { name: string; url: string };

export type CalendarCreds = {
  server_url: string;
  username: string;
  password: string;
};

export function listConnections(): Promise<Connection[]> {
  return authedFetch<Connection[]>("/v1/me/calendar/connections");
}

/** Probe a server with these credentials and list what is on it. Stores nothing. */
export function listCalendars(creds: CalendarCreds): Promise<CalendarInfo[]> {
  return authedFetch<CalendarInfo[]>("/v1/me/calendar/calendars", {
    method: "POST",
    body: JSON.stringify(creds),
  });
}

export function connectCalendar(
  body: CalendarCreds & { calendar_url: string; calendar_name?: string | null },
): Promise<Connection> {
  return authedFetch<Connection>("/v1/me/calendar/connections", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Sync one account. */
export function syncConnection(id: string): Promise<{ synced: number }> {
  return authedFetch<{ synced: number }>(
    `/v1/me/calendar/connections/${id}/sync`,
    { method: "POST" },
  );
}

/** Sync every account. One failing does not stop the others. */
export function syncAllCalendars(): Promise<{ synced: number }> {
  return authedFetch<{ synced: number }>("/v1/me/calendar/sync", {
    method: "POST",
  });
}

/** Make this the calendar bookings are written back to. */
export function setMirrorTarget(id: string): Promise<void> {
  return authedFetch<void>(`/v1/me/calendar/connections/${id}/mirror`, {
    method: "PUT",
  });
}

/** Recolour a connected calendar, whose colour was picked by cycling a palette at connect time. */
export function setConnectionColor(id: string, color: string): Promise<void> {
  return authedFetch<void>(`/v1/me/calendar/connections/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ color }),
  });
}

export function disconnectCalendar(id: string): Promise<void> {
  return authedFetch<void>(`/v1/me/calendar/connections/${id}`, {
    method: "DELETE",
  });
}
