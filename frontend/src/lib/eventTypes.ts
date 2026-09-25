// Event-type API client (authenticated).

import { authedFetch } from "@/lib/auth";

export type BookingQuestion = {
  id: string;
  label: string;
  type: "text" | "textarea" | "phone" | "select" | "checkbox";
  required: boolean;
  options: string[];
};

export type EventType = {
  id: string;
  organization_id: string;
  organization_slug: string;
  slug: string;
  title: string;
  description: string | null;
  duration_min: number;
  slot_interval_min: number;
  buffer_before_min: number;
  buffer_after_min: number;
  min_notice_min: number;
  date_window_days: number;
  max_per_day: number | null;
  location_type: string;
  active: boolean;
  questions: BookingQuestion[];
  kind: string;
  host_ids: string[];
  capacity: number;
  redirect_url: string | null;
};

export type EventTypeInput = {
  title: string;
  description: string | null;
  duration_min: number;
  slot_interval_min: number;
  buffer_before_min: number;
  buffer_after_min: number;
  min_notice_min: number;
  date_window_days: number;
  max_per_day: number | null;
  location_type: string;
  active: boolean;
  questions: BookingQuestion[];
  kind: string;
  host_ids: string[];
  capacity: number;
  redirect_url: string | null;
};

/**
 * Fields the server owns. Everything else on an event type is the client's to send back.
 */
type ServerAssigned = "id" | "organization_id" | "organization_slug" | "slug";

/**
 * `EventTypeInput` must cover every editable field of `EventType`, and this line is what says so.
 *
 * `PUT /v1/me/event-types/{id}` REPLACES the object: a field missing from the body is not left
 * alone, it goes back to the schema default. `description` was missing from this type until
 * 2026-08-30, so every save — and every flick of the active switch, which posts the same body —
 * silently blanked a field that the public booking page renders (`app/[org]/page.tsx`).
 *
 * A test could only ever have caught the field someone thought to write a test for. This fails the
 * type check instead, on the next field added to `EventType` and forgotten here.
 */
type _EveryEditableFieldIsSendable = Exclude<
  keyof Omit<EventType, ServerAssigned>,
  keyof EventTypeInput
> extends never
  ? true
  : never;
const _everyEditableFieldIsSendable: _EveryEditableFieldIsSendable = true;
void _everyEditableFieldIsSendable;

/**
 * The body to send back for an event type, from anything that carries its fields.
 *
 * Lives here rather than in the page because the page cannot be tested — this suite renders no
 * components — and because all three callers need it: saving the form, opening the editor, and
 * toggling `active` from the list. That last one is why a dropped field is expensive: it looks
 * like a switch, and it rewrites the whole object.
 */
export function toEventTypeInput(x: EventTypeInput): EventTypeInput {
  return {
    title: x.title,
    description: x.description,
    duration_min: x.duration_min,
    slot_interval_min: x.slot_interval_min,
    buffer_before_min: x.buffer_before_min,
    buffer_after_min: x.buffer_after_min,
    min_notice_min: x.min_notice_min,
    date_window_days: x.date_window_days,
    max_per_day: x.max_per_day,
    location_type: x.location_type,
    active: x.active,
    questions: x.questions,
    kind: x.kind,
    host_ids: x.host_ids,
    capacity: x.capacity,
    redirect_url: x.redirect_url,
  };
}

export const LOCATION_LABELS: Record<string, string> = {
  google_meet: "Google Meet",
  ms_teams: "Microsoft Teams",
  zoom: "Zoom",
  in_person: "In person",
  phone: "Phone",
  custom: "Custom",
};

export function listEventTypes(): Promise<EventType[]> {
  return authedFetch<EventType[]>("/v1/me/event-types");
}

export function createEventType(body: EventTypeInput): Promise<{ id: string }> {
  return authedFetch<{ id: string }>("/v1/me/event-types", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateEventType(id: string, body: EventTypeInput): Promise<EventType> {
  return authedFetch<EventType>(`/v1/me/event-types/${id}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function deleteEventType(id: string): Promise<void> {
  return authedFetch<void>(`/v1/me/event-types/${id}`, { method: "DELETE" });
}

/** The public booking URL for an event type (readable slugs), built from the current origin. */
export function publicLink(eventType: EventType): string {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return `${origin}/${eventType.organization_slug}/${eventType.slug}`;
}

/** An <iframe> snippet that embeds the booking widget on any website. */
export function embedSnippet(eventType: EventType): string {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const src = `${origin}/embed/${eventType.organization_slug}/${eventType.slug}`;
  return `<iframe src="${src}" width="100%" height="720" frameborder="0" style="border:0"></iframe>`;
}
