import { describe, expect, it } from "vitest";
import { parseQuickAdd } from "@/lib/quickAdd";

// A fixed reference date keeps chrono deterministic: Mon 2026-03-16, 08:00 local.
const REF = new Date(2026, 2, 16, 8, 0, 0);

describe("parseQuickAdd", () => {
  it("returns null for text with no date/time", () => {
    expect(parseQuickAdd("just a title", "en", REF)).toBeNull();
    expect(parseQuickAdd("   ", "en", REF)).toBeNull();
  });

  it("parses title, time, duration and location (EN)", () => {
    const r = parseQuickAdd("Lunch with Sam tomorrow 12:30 for 1h at Café Lumen", "en", REF);
    expect(r).not.toBeNull();
    expect(r!.title).toBe("Lunch with Sam");
    expect(r!.location).toBe("Café Lumen");
    expect(r!.date).toBe("2026-03-17");
    expect(r!.start).toBe("12:30");
    expect(r!.end).toBe("13:30");
    expect(r!.allDay).toBe(false);
  });

  it("treats a date without a time as all-day", () => {
    const r = parseQuickAdd("Project deadline friday", "en", REF);
    expect(r).not.toBeNull();
    expect(r!.allDay).toBe(true);
  });

  it("extracts a weekly recurrence rule and strips the phrase from the title", () => {
    const r = parseQuickAdd("Standup every monday 9am", "en", REF);
    expect(r).not.toBeNull();
    expect(r!.rrule).toBe("FREQ=WEEKLY;BYDAY=MO");
    expect(r!.start).toBe("09:00");
    expect(r!.title.toLowerCase()).not.toContain("every monday");
  });

  it("parses a French phrase with its locale", () => {
    const r = parseQuickAdd("Déjeuner demain 12:30 pendant 1h", "fr", REF);
    expect(r).not.toBeNull();
    expect(r!.date).toBe("2026-03-17");
    expect(r!.start).toBe("12:30");
    expect(r!.end).toBe("13:30");
  });
});
