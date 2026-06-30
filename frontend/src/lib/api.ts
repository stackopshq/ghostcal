// Typed client for the GhostCal API.

// Resolve the API base URL.
// - In the browser: same-origin "/api", proxied to the backend by Next's rewrites. The browser
//   only ever talks to this origin, so the backend port need not be exposed and there is no CORS.
// - On the server (SSR): reach the backend directly.
export function resolveBaseUrl(): string {
  if (typeof window !== "undefined") return "/api";
  return process.env.API_INTERNAL_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
}

const BASE_URL = resolveBaseUrl();

export type BookingQuestion = {
  id: string;
  label: string;
  type: "text" | "textarea" | "phone" | "select" | "checkbox";
  required: boolean;
  options: string[];
};

export type EventType = {
  id: string;
  title: string;
  duration_min: number;
  location_type: string;
  host_name: string;
  questions: BookingQuestion[];
  redirect_url: string | null;
  // Org zero-knowledge public key — the booking page seals the invitee's details to it.
  zk_public_key: string | null;
};

export type Slot = { start: string; end: string };

export type Booking = {
  id: string;
  start_at: string;
  end_at: string;
  status: string;
};

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new ApiError(res.status, detail || res.statusText);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export type ManageBooking = {
  event_title: string;
  host_name: string;
  organization_slug: string;
  event_slug: string;
  invitee_name: string | null;
  invitee_timezone: string;
  duration_min: number;
  location_type: string;
  start_at: string;
  end_at: string;
  status: string;
};

export function getManagedBooking(token: string): Promise<ManageBooking> {
  return request<ManageBooking>(`/v1/bookings/manage/${token}`);
}

export function cancelManagedBooking(token: string): Promise<void> {
  return request<void>(`/v1/bookings/manage/${token}/cancel`, { method: "POST" });
}

export function rescheduleManagedBooking(token: string, startAt: string): Promise<Booking> {
  return request<Booking>(`/v1/bookings/manage/${token}/reschedule`, {
    method: "POST",
    body: JSON.stringify({ start_at: startAt }),
  });
}

export type PublicEventType = {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  duration_min: number;
  location_type: string;
};

export type BookingPage = {
  organization_name: string;
  event_types: PublicEventType[];
};

export function getBookingPage(org: string): Promise<BookingPage> {
  return request<BookingPage>(`/v1/orgs/${org}/event-types`);
}

export function getEventType(org: string, event: string): Promise<EventType> {
  return request<EventType>(`/v1/orgs/${org}/event-types/${event}`);
}

export function getAvailability(
  org: string,
  event: string,
  from: string,
  to: string,
): Promise<{ event_type_id: string; slots: Slot[] }> {
  const qs = new URLSearchParams({ from, to });
  return request(`/v1/orgs/${org}/event-types/${event}/availability?${qs}`);
}

export type InvitationPreview = {
  organization_id: string;
  organization_name: string;
  email: string;
  role: string;
  // Org private key sealed under the link-fragment grant key (zero-knowledge team sharing).
  wrapped_org_key: string | null;
};

export function getInvitationPreview(token: string): Promise<InvitationPreview> {
  return request<InvitationPreview>(`/v1/invitations/${token}`);
}

export type PollOption = { id: string; start_at: string; end_at: string; votes: number };

export type PublicPoll = {
  slug: string;
  title: string;
  duration_min: number;
  location_type: string;
  status: string;
  owner_name: string;
  finalized_option_id: string | null;
  options: PollOption[];
};

export function getPublicPoll(slug: string): Promise<PublicPoll> {
  return request<PublicPoll>(`/v1/polls/${slug}`);
}

export function votePoll(
  slug: string,
  body: { voter_name: string; voter_email: string; option_ids: string[] },
): Promise<void> {
  return request<void>(`/v1/polls/${slug}/votes`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function createBooking(
  org: string,
  event: string,
  payload: {
    start_at: string;
    // No invitee_name/answers: they are sealed client-side into invitee_private (zero-knowledge).
    invitee_email: string;
    invitee_timezone: string;
    guest_emails?: string[];
    invitee_private?: string | null;
  },
): Promise<Booking> {
  return request<Booking>(`/v1/orgs/${org}/event-types/${event}/bookings`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
