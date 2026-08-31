/**
 * A shared calendar must show the entries it cannot read.
 *
 * `/c/[token]` is the only public screen built for judging whether its owner is free. Until
 * 2026-08-30 it dropped every entry whose title failed to decrypt, so a link whose key no longer
 * fitted rendered a full week as "Nothing on this calendar yet" — and a busy hour as an empty one.
 * The visitor has no account, no other view, and no way to tell the two apart.
 *
 * These tests pin the rule the other three screens already keep: a visible gap, never an absent row.
 */

import { describe, expect, it } from "vitest";

import { type PublicEvent, publicCalendarRows } from "@/lib/links";

function event(start: string): PublicEvent {
  return {
    start_at: start,
    end_at: start,
    all_day: false,
    timezone: "UTC",
    rrule: null,
    exdates: [],
    content_sealed: `sealed-${start}`,
  };
}

describe("publicCalendarRows", () => {
  it("keeps an entry whose title did not decrypt, and marks it locked", () => {
    const events = [event("2026-09-01T09:00:00Z"), event("2026-09-01T14:00:00Z")];
    // Only the second one opened.
    const rows = publicCalendarRows(events, new Map([[1, "Design review"]]));

    expect(rows).toHaveLength(2);
    expect(rows[0].title).toBeNull();
    expect(rows[0].event.start_at).toBe("2026-09-01T09:00:00Z");
    expect(rows[1].title).toBe("Design review");
  });

  it("returns every entry when the key opens none of them", () => {
    // The case that rendered as an empty calendar: a revoked or mistyped fragment.
    const events = ["2026-09-02T08:00:00Z", "2026-09-02T09:00:00Z"].map(event);
    const rows = publicCalendarRows(events, new Map());

    expect(rows).toHaveLength(2);
    expect(rows.every((r) => r.title === null)).toBe(true);
  });

  it("orders by start time regardless of which entries opened", () => {
    const events = [
      event("2026-09-03T17:00:00Z"),
      event("2026-09-03T08:00:00Z"),
      event("2026-09-03T12:00:00Z"),
    ];
    const rows = publicCalendarRows(events, new Map([[0, "Evening"]]));

    expect(rows.map((r) => r.event.start_at)).toEqual([
      "2026-09-03T08:00:00Z",
      "2026-09-03T12:00:00Z",
      "2026-09-03T17:00:00Z",
    ]);
    // The one that opened is last by time, so a sort that only walked the opened ones would
    // have put it first.
    expect(rows[2].title).toBe("Evening");
  });

  it("is empty only when the calendar is", () => {
    expect(publicCalendarRows([], new Map())).toEqual([]);
  });
});
