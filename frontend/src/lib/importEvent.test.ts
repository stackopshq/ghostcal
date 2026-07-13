import { describe, expect, it } from "vitest";
import {
  type ImportedEvent,
  buildImportUrl,
  parseImportUrl,
  toDraftFields,
} from "@/lib/importEvent";

// A deep link comes from another application. That makes it input, and trusting input is a decision
// rather than a default — so the tests here care mostly about what happens when it is wrong.

const EVENT: ImportedEvent = {
  title: "Sprint review",
  start: "2050-06-01T15:00:00.000Z",
  end: "2050-06-01T16:00:00.000Z",
  location: "Room 3",
  description: "Bring the deck",
  rrule: "FREQ=WEEKLY;BYDAY=MO",
};

describe("the structured import link", () => {
  it("round-trips everything an .ics can carry", () => {
    const url = buildImportUrl("https://cal.example.com", EVENT);
    const parsed = parseImportUrl(new URL(url).search);

    // The whole reason this exists: a natural-language string would have dropped the end, the
    // location and the recurrence — the three things the sender had already stated exactly.
    expect(parsed).toEqual({ ...EVENT, allDay: false });
  });

  it("survives a title that would break a URL", () => {
    const url = buildImportUrl("https://cal.example.com", {
      title: "Lunch & learn — 50% off? #food",
      start: EVENT.start,
    });
    expect(parseImportUrl(new URL(url).search)?.title).toBe(
      "Lunch & learn — 50% off? #food",
    );
  });

  it("ignores a URL that is not an import", () => {
    expect(parseImportUrl("?add=Dentist%20tomorrow")).toBeNull();
    expect(parseImportUrl("")).toBeNull();
  });

  it("refuses a malformed event rather than half-filling the form", () => {
    // A form the user has to correct is worse than no prefill: they trust what they are shown.
    expect(parseImportUrl("?import=1&title=X")).toBeNull(); // no start
    expect(parseImportUrl("?import=1&start=not-a-date")).toBeNull();
    expect(
      parseImportUrl("?import=1&start=2050-06-01T15:00:00Z&end=nonsense"),
    ).toBeNull();
  });

  it("refuses an end before its start — that is not a shorter event, it is a broken one", () => {
    expect(
      parseImportUrl(
        "?import=1&start=2050-06-01T15:00:00Z&end=2050-06-01T14:00:00Z",
      ),
    ).toBeNull();
  });
});

describe("toDraftFields", () => {
  it("fills the form in the user's own local time", () => {
    const start = new Date("2050-06-01T15:00:00.000Z");
    const fields = toDraftFields(EVENT);

    // Local, not UTC: the form shows wall-clock times, and an event at 15:00Z is not at 15:00 for
    // most of the people who will read it.
    expect(fields.date).toBe(
      `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, "0")}-${String(start.getDate()).padStart(2, "0")}`,
    );
    expect(fields.start).toBe(
      `${String(start.getHours()).padStart(2, "0")}:${String(start.getMinutes()).padStart(2, "0")}`,
    );
    expect(fields.rrule).toBe("FREQ=WEEKLY;BYDAY=MO");
    expect(fields.location).toBe("Room 3");
  });

  it("gives an event with no end an hour, rather than a zero-length one", () => {
    const fields = toDraftFields({ title: "X", start: "2050-06-01T09:00:00.000Z" });
    const start = new Date("2050-06-01T09:00:00.000Z");
    const expected = new Date(start.getTime() + 3600_000);
    expect(fields.end).toBe(
      `${String(expected.getHours()).padStart(2, "0")}:${String(expected.getMinutes()).padStart(2, "0")}`,
    );
  });
});
