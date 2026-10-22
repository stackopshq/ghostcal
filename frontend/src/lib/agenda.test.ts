import { afterEach, describe, expect, it, vi } from "vitest";

const authedFetch = vi.fn<(...args: unknown[]) => Promise<unknown>>(async () => undefined);
vi.mock("@/lib/auth", () => ({ authedFetch: (...args: unknown[]) => authedFetch(...args) }));

import { renameCalendar, setCalendarColor } from "@/lib/agenda";

afterEach(() => authedFetch.mockClear());

describe("calendar PATCH", () => {
  it("renames with the name alone, trimmed, so the colour is left untouched", async () => {
    await renameCalendar("cal-1", "  My calendar ");
    const [path, opts] = authedFetch.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/v1/me/calendars/cal-1");
    expect(opts.method).toBe("PATCH");
    expect(JSON.parse(opts.body as string)).toEqual({ name: "My calendar" });
  });

  it("recolours with the colour alone, so the name is left untouched", async () => {
    await setCalendarColor("cal-1", "#ff2d95");
    const [, opts] = authedFetch.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(opts.body as string)).toEqual({ color: "#ff2d95" });
  });
});
