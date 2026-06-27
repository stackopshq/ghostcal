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

export type EventType = {
  id: string;
  title: string;
  duration_min: number;
  location_type: string;
  host_name: string;
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
  return res.json() as Promise<T>;
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

export function createBooking(
  org: string,
  event: string,
  payload: {
    start_at: string;
    invitee_name: string;
    invitee_email: string;
    invitee_timezone: string;
  },
): Promise<Booking> {
  return request<Booking>(`/v1/orgs/${org}/event-types/${event}/bookings`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
