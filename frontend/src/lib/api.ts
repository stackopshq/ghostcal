// Typed client for the GhostCal API.

// Resolve the API base URL:
// 1. NEXT_PUBLIC_API_URL if set (explicit override);
// 2. in the browser, the same host that served the page, on port 8000 (works when accessed
//    from another machine — "localhost" would wrongly mean the visitor's own machine);
// 3. localhost:8000 on the server (SSR) and as a last resort.
function resolveBaseUrl(): string {
  const override = process.env.NEXT_PUBLIC_API_URL;
  if (override) return override.replace(/\/$/, "");
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return "http://localhost:8000";
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
