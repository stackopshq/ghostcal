// A structured event handed over by a sibling app (GhostMail's "add to calendar", an .ics
// attachment, a meeting invitation).
//
// The existing bridge passes a natural-language string to the quick-add box, which is right when all
// you have is a sentence in an email. It is wrong when you have an .ics: a sentence cannot carry an
// end time, a location and a recurrence rule, so re-parsing one out of prose would throw away
// information the sender had already stated exactly.
//
// So there is a second, structured door. It stays a **deep link**: no cross-app backend call, and
// the event is still sealed in this browser when the user confirms. GhostMail hands over what it
// read; GhostCal decides nothing on its own and saves nothing until the user says so.

/** What a sibling app can hand over. Everything but the start is optional. */
export type ImportedEvent = {
  title: string;
  /** ISO 8601. The only field that must be there — an event with no start is not an event. */
  start: string;
  end?: string;
  location?: string;
  description?: string;
  /** RFC 5545, e.g. "FREQ=WEEKLY;BYDAY=MO". */
  rrule?: string;
  allDay?: boolean;
};

// Long enough for a real description, short enough that the URL survives every browser and proxy in
// between. Anything longer is truncated rather than dropped: half a description beats none.
const MAX_DESCRIPTION = 1000;
const MAX_TEXT = 200;

/** Build the deep-link a sibling app opens. Exported so the other side has one place to copy. */
export function buildImportUrl(origin: string, event: ImportedEvent): string {
  const params = new URLSearchParams({
    import: "1",
    title: event.title.slice(0, MAX_TEXT),
  });
  params.set("start", event.start);
  if (event.end) params.set("end", event.end);
  if (event.location) params.set("location", event.location.slice(0, MAX_TEXT));
  if (event.description)
    params.set("description", event.description.slice(0, MAX_DESCRIPTION));
  if (event.rrule) params.set("rrule", event.rrule);
  if (event.allDay) params.set("allday", "1");
  return `${origin.replace(/\/$/, "")}/dashboard/calendar?${params}`;
}

/**
 * Read a structured event out of the URL, or null if there isn't one.
 *
 * Anything malformed yields null rather than a half-filled form. A deep link comes from another
 * application, which makes it input, which makes trusting it a decision — and a prefilled form the
 * user has to correct is worse than no prefill at all.
 */
export function parseImportUrl(search: string): ImportedEvent | null {
  const params = new URLSearchParams(search);
  if (params.get("import") !== "1") return null;

  const start = params.get("start");
  if (!start || Number.isNaN(Date.parse(start))) return null;

  const end = params.get("end");
  if (end && Number.isNaN(Date.parse(end))) return null;
  // An end before its start is not a shorter event; it is a broken one.
  if (end && Date.parse(end) < Date.parse(start)) return null;

  return {
    title: (params.get("title") ?? "").slice(0, MAX_TEXT),
    start,
    end: end ?? undefined,
    location: params.get("location")?.slice(0, MAX_TEXT) || undefined,
    description:
      params.get("description")?.slice(0, MAX_DESCRIPTION) || undefined,
    rrule: params.get("rrule") || undefined,
    allDay: params.get("allday") === "1",
  };
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

/** The imported event as the event form wants it: local date and wall-clock times. */
export function toDraftFields(event: ImportedEvent): {
  title: string;
  description: string;
  location: string;
  date: string;
  start: string;
  end: string;
  allDay: boolean;
  rrule: string;
} {
  const start = new Date(event.start);
  // No end given? An hour is the convention every calendar uses, and the user can change it before
  // saving — which they have to do anyway, because nothing here saves on its own.
  const end = event.end
    ? new Date(event.end)
    : new Date(start.getTime() + 60 * 60 * 1000);

  return {
    title: event.title,
    description: event.description ?? "",
    location: event.location ?? "",
    date: `${start.getFullYear()}-${pad(start.getMonth() + 1)}-${pad(start.getDate())}`,
    start: `${pad(start.getHours())}:${pad(start.getMinutes())}`,
    end: `${pad(end.getHours())}:${pad(end.getMinutes())}`,
    allDay: event.allDay ?? false,
    rrule: event.rrule ?? "",
  };
}
