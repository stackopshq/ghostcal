import { describe, expect, it } from "vitest";
import { layoutLanes } from "@/lib/eventLayout";

const iv = (start: number, end: number) => ({ start, end });

describe("layoutLanes", () => {
  it("returns nothing for no events", () => {
    expect(layoutLanes([])).toEqual([]);
  });

  it("gives a lone event the full width", () => {
    expect(layoutLanes([iv(9, 10)])).toEqual([{ lane: 0, lanes: 1 }]);
  });

  it("puts two simultaneous events side by side", () => {
    expect(layoutLanes([iv(9, 10), iv(9, 10)])).toEqual([
      { lane: 0, lanes: 2 },
      { lane: 1, lanes: 2 },
    ]);
  });

  it("does not split events that only touch", () => {
    expect(layoutLanes([iv(9, 10), iv(10, 11)])).toEqual([
      { lane: 0, lanes: 1 },
      { lane: 0, lanes: 1 },
    ]);
  });

  it("reuses a freed lane and keeps one width across a transitive cluster", () => {
    // A 9-11 overlaps B 10-12 and C 11-13; B overlaps C. C can reuse A's lane.
    expect(layoutLanes([iv(9, 11), iv(10, 12), iv(11, 13)])).toEqual([
      { lane: 0, lanes: 2 },
      { lane: 1, lanes: 2 },
      { lane: 0, lanes: 2 },
    ]);
  });

  it("returns lanes in input order whatever the start order", () => {
    expect(layoutLanes([iv(10, 11), iv(9, 12)])).toEqual([
      { lane: 1, lanes: 2 },
      { lane: 0, lanes: 2 },
    ]);
  });

  it("starts a fresh cluster after a gap", () => {
    expect(layoutLanes([iv(9, 10), iv(9, 10), iv(14, 15)])).toEqual([
      { lane: 0, lanes: 2 },
      { lane: 1, lanes: 2 },
      { lane: 0, lanes: 1 },
    ]);
  });

  it("uses three lanes for three simultaneous events", () => {
    const lanes = layoutLanes([iv(9, 10), iv(9, 10), iv(9, 10)]);
    expect(lanes.map((l) => l.lane).sort()).toEqual([0, 1, 2]);
    expect(lanes.every((l) => l.lanes === 3)).toBe(true);
  });
});
