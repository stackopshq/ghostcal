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
};

export type EventTypeInput = {
  title: string;
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
};

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
