// Account lifecycle client: erasure (GDPR art. 17), portability (art. 20) and retention.
//
// The export is assembled HERE, in the browser, and that is the whole point (ADR-0006 §5). The
// server holds the event/task/invitee content as ciphertext sealed to each organization's public
// key and can never open it — an export built server-side would be a file full of base64. So the
// API hands over the record set with the sealed blobs verbatim, and this module unseals them with
// the org keys the browser already unlocked at login, then writes the archive.

import { authedFetch } from "@/lib/auth";
import {
  type EventContent,
  type InviteePrivate,
  type TaskContent,
  getUnlockedKeys,
  openContent,
  openWithOrgKeys,
  openInviteePrivate,
  openTaskContent,
} from "@/lib/zk";

// --- API -------------------------------------------------------------------------------------

export type Retention = { booking_retention_days: number | null };

export function getRetention(): Promise<Retention> {
  return authedFetch<Retention>("/v1/me/organization/retention");
}

export function setRetention(days: number | null): Promise<Retention> {
  return authedFetch<Retention>("/v1/me/organization/retention", {
    method: "PUT",
    body: JSON.stringify({ booking_retention_days: days }),
  });
}

export function deleteAccount(
  emailConfirmation: string,
  password: string | null,
): Promise<void> {
  return authedFetch<void>("/v1/me/account", {
    method: "DELETE",
    body: JSON.stringify({ email_confirmation: emailConfirmation, password }),
  });
}

// --- The export payload, as the server hands it over ------------------------------------------
//
// Fields named *_sealed are ciphertext. Nothing else in here is secret: the API deliberately sends
// no password hash, no token, no webhook secret and no CalDAV password.

export type RawEvent = {
  id: string;
  calendar_id: string;
  start_at: string;
  end_at: string;
  all_day: boolean;
  timezone: string;
  rrule: string | null;
  exdates: string[];
  status: string;
  reminder_minutes: number | null;
  content_sealed: string | null;
};

export type RawCalendar = {
  id: string;
  organization_id: string;
  name: string;
  color: string;
  is_default: boolean;
  events: RawEvent[];
};

export type RawTask = {
  id: string;
  organization_id: string;
  due_at: string | null;
  completed: boolean;
  completed_at: string | null;
  reminder_minutes: number | null;
  content_sealed: string | null;
};

export type RawBooking = {
  id: string;
  organization_id: string;
  event_type_title: string;
  start_at: string;
  end_at: string;
  status: string;
  invitee_email: string;
  invitee_timezone: string;
  location: string | null;
  invitee_private_sealed: string | null;
};

export type AccountExport = {
  profile: {
    id: string;
    email: string;
    name: string;
    timezone: string;
    email_verified_at: string | null;
    created_at: string;
  };
  organizations: { id: string; name: string; slug: string; role: string }[];
  calendars: RawCalendar[];
  tasks: RawTask[];
  bookings: RawBooking[];
  event_types: unknown[];
  schedules: unknown[];
  subscriptions: unknown[];
  caldav_connections: unknown[];
};

export function fetchExport(): Promise<AccountExport> {
  return authedFetch<AccountExport>("/v1/me/export");
}

// --- Unsealing -------------------------------------------------------------------------------

/** Opened content, or null when this org's key is locked — never a thrown export. */
async function open<T>(
  blob: string | null,
  organizationId: string,
  opener: (blob: string, privateKey: string) => Promise<T>,
): Promise<T | null> {
  if (!blob) return null;
  const keys = getUnlockedKeys(organizationId);
  if (!keys) return null;
  try {
    // Retired generations included: a record sealed before a rotation and not yet re-sealed still
    // needs the key it was sealed under (ADR-0007).
    return await openWithOrgKeys(keys, blob, opener);
  } catch {
    // A blob we hold no working key for. Report it in the archive rather than losing the record:
    // a partial export the user can see the holes in beats a silent one.
    return null;
  }
}

export type OpenedExport = {
  profile: AccountExport["profile"];
  organizations: AccountExport["organizations"];
  calendars: {
    id: string;
    name: string;
    color: string;
    events: (Omit<RawEvent, "content_sealed"> & {
      content: EventContent | null;
    })[];
  }[];
  tasks: (Omit<RawTask, "content_sealed"> & { content: TaskContent | null })[];
  bookings: (Omit<RawBooking, "invitee_private_sealed"> & {
    invitee_private: InviteePrivate | null;
  })[];
  event_types: unknown[];
  schedules: unknown[];
  subscriptions: unknown[];
  caldav_connections: unknown[];
  /** How many sealed blobs could not be opened — the org's key was locked or did not fit. */
  unopened: number;
};

export async function openExport(raw: AccountExport): Promise<OpenedExport> {
  let unopened = 0;
  const count = <T>(value: T | null, sealed: string | null): T | null => {
    if (sealed && value === null) unopened += 1;
    return value;
  };

  const calendars = await Promise.all(
    raw.calendars.map(async (calendar) => ({
      id: calendar.id,
      name: calendar.name,
      color: calendar.color,
      events: await Promise.all(
        calendar.events.map(async ({ content_sealed, ...event }) => ({
          ...event,
          content: count(
            await open(content_sealed, calendar.organization_id, openContent),
            content_sealed,
          ),
        })),
      ),
    })),
  );

  const tasks = await Promise.all(
    raw.tasks.map(async ({ content_sealed, ...task }) => ({
      ...task,
      content: count(
        await open(content_sealed, task.organization_id, openTaskContent),
        content_sealed,
      ),
    })),
  );

  const bookings = await Promise.all(
    raw.bookings.map(async ({ invitee_private_sealed, ...booking }) => ({
      ...booking,
      invitee_private: count(
        // openInviteePrivate still takes a public key it does not use; drop it here rather than
        // thread a dummy through the generic opener.
        await open(
          invitee_private_sealed,
          booking.organization_id,
          (blob, privateKey) => openInviteePrivate(blob, "", privateKey),
        ),
        invitee_private_sealed,
      ),
    })),
  );

  return {
    profile: raw.profile,
    organizations: raw.organizations,
    calendars,
    tasks,
    bookings,
    event_types: raw.event_types,
    schedules: raw.schedules,
    subscriptions: raw.subscriptions,
    caldav_connections: raw.caldav_connections,
    unopened,
  };
}

// --- iCalendar ---------------------------------------------------------------------------------

function icsEscape(value: string): string {
  return value
    .replace(/\\/g, "\\\\")
    .replace(/;/g, "\\;")
    .replace(/,/g, "\\,")
    .replace(/\n/g, "\\n");
}

function icsStamp(iso: string): string {
  return `${new Date(iso).toISOString().replace(/[-:]/g, "").split(".")[0]}Z`;
}

/** The calendar half of the archive: decrypted events, in a format any calendar app can read. */
export function buildIcs(exported: OpenedExport): string {
  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//GhostCal//Export//EN",
    "CALSCALE:GREGORIAN",
  ];

  for (const calendar of exported.calendars) {
    for (const event of calendar.events) {
      lines.push(
        "BEGIN:VEVENT",
        `UID:${event.id}@ghostcal`,
        `DTSTAMP:${icsStamp(event.start_at)}`,
        `DTSTART:${icsStamp(event.start_at)}`,
        `DTEND:${icsStamp(event.end_at)}`,
        // A sealed event we could not open still belongs in the archive — as a hole the user can see.
        `SUMMARY:${icsEscape(event.content?.title ?? "(encrypted: key locked)")}`,
      );
      if (event.content?.location)
        lines.push(`LOCATION:${icsEscape(event.content.location)}`);
      if (event.content?.description)
        lines.push(`DESCRIPTION:${icsEscape(event.content.description)}`);
      if (event.rrule) lines.push(`RRULE:${event.rrule}`);
      lines.push("END:VEVENT");
    }
  }

  lines.push("END:VCALENDAR");
  return lines.join("\r\n");
}

export function download(
  filename: string,
  content: string,
  mime: string,
): void {
  const url = URL.createObjectURL(new Blob([content], { type: mime }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

/** Fetch, unseal in-browser, and write both halves of the archive. Returns how many stayed sealed. */
export async function downloadExport(): Promise<number> {
  const exported = await openExport(await fetchExport());
  download(
    "ghostcal-export.json",
    JSON.stringify(exported, null, 2),
    "application/json",
  );
  download("ghostcal-calendar.ics", buildIcs(exported), "text/calendar");
  return exported.unopened;
}
