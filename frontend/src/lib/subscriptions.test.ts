import { afterEach, describe, expect, it, vi } from "vitest";

// Guard the client-side half of the API contract: these paths must match what the backend mounts
// (a prefix drift here is exactly the silent 404 that shipped once). The backend half is pinned by
// test_api.py's OpenAPI-path assertions.
const authedFetch = vi.fn(async () => undefined);
vi.mock("@/lib/auth", () => ({ authedFetch: (...args: unknown[]) => authedFetch(...args) }));

import {
  addSubscription,
  deleteSubscription,
  listSubscriptions,
  refreshSubscription,
} from "@/lib/subscriptions";

afterEach(() => authedFetch.mockClear());

describe("subscriptions API client", () => {
  it("lists under /v1/me/calendar/subscriptions", async () => {
    await listSubscriptions();
    expect(authedFetch).toHaveBeenCalledWith("/v1/me/calendar/subscriptions");
  });

  it("adds via POST to the calendar-scoped path", async () => {
    await addSubscription({ name: "Holidays", url: "https://example.com/h.ics", color: "#fff" });
    const [path, opts] = authedFetch.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/v1/me/calendar/subscriptions");
    expect(opts.method).toBe("POST");
    expect(JSON.parse(opts.body as string)).toMatchObject({ name: "Holidays" });
  });

  it("refreshes and deletes a specific subscription by id", async () => {
    await refreshSubscription("abc-123");
    expect(authedFetch).toHaveBeenCalledWith(
      "/v1/me/calendar/subscriptions/abc-123/refresh",
      expect.objectContaining({ method: "POST" }),
    );
    authedFetch.mockClear();
    await deleteSubscription("abc-123");
    expect(authedFetch).toHaveBeenCalledWith(
      "/v1/me/calendar/subscriptions/abc-123",
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});
