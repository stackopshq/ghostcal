/**
 * Sending an event type back must not lose any of it.
 *
 * `PUT /v1/me/event-types/{id}` REPLACES the object. A field absent from the body is not left
 * alone — the schema default takes its place. So the mapper that builds that body is the one place
 * where forgetting a field costs data, silently, with a 200 in reply.
 *
 * `description` was forgotten from 2026-06 until 2026-08-30. It is rendered on the public booking
 * page, and it was wiped by every save AND by every flick of the `active` switch in the list, which
 * posts the same full body. Nothing failed; the text simply stopped being there.
 *
 * These tests walk the object rather than naming fields, because a test that names fields only ever
 * catches the field someone remembered. The type-level assertion in `eventTypes.ts` covers the
 * other half: adding a field to `EventType` and forgetting `EventTypeInput` fails `tsc`.
 */

import { describe, expect, it } from "vitest";

import {
  type EventType,
  type EventTypeInput,
  toEventTypeInput,
} from "@/lib/eventTypes";

/** Assigned by the server; the client has nothing to send back for these. */
const SERVER_ASSIGNED = new Set([
  "id",
  "organization_id",
  "organization_slug",
  "slug",
]);

/** Every field set to something distinctive, so a default silently replacing one is visible. */
const FULL: EventType = {
  id: "5f0f7a1e-0000-4000-8000-000000000001",
  organization_id: "5f0f7a1e-0000-4000-8000-000000000002",
  organization_slug: "acme",
  slug: "intro-call",
  title: "Intro call",
  description: "Fifteen minutes to see whether we should talk longer.",
  duration_min: 45,
  slot_interval_min: 20,
  buffer_before_min: 5,
  buffer_after_min: 10,
  min_notice_min: 120,
  date_window_days: 30,
  max_per_day: 4,
  location_type: "in_person",
  active: false,
  questions: [
    {
      id: "q1",
      label: "What would you like to cover?",
      type: "textarea",
      required: true,
      options: [],
    },
  ],
  kind: "collective",
  host_ids: ["5f0f7a1e-0000-4000-8000-000000000003"],
  capacity: 8,
  redirect_url: "https://example.test/thanks",
};

describe("toEventTypeInput", () => {
  it("carries every editable field back to the server", () => {
    const body = toEventTypeInput(FULL) as Record<string, unknown>;

    for (const [field, value] of Object.entries(FULL)) {
      if (SERVER_ASSIGNED.has(field)) continue;
      expect(
        body[field],
        `\`${field}\` never reaches the server, so a PUT resets it to its default`,
      ).toEqual(value);
    }
  });

  it("sends nothing the server did not ask for", () => {
    const body = toEventTypeInput(FULL) as Record<string, unknown>;
    for (const field of Object.keys(body)) {
      expect(SERVER_ASSIGNED.has(field)).toBe(false);
    }
  });

  it("survives the round trip the active switch makes", () => {
    // The list toggles `active` and posts the whole object back. Everything else must come out
    // the other side untouched, which is exactly what stopped being true for `description`.
    const before = toEventTypeInput(FULL);
    const after = toEventTypeInput({ ...FULL, active: !FULL.active });

    expect(after.active).toBe(true);
    expect(after.description).toBe(FULL.description);
    // Put `active` back and the two bodies must be indistinguishable: the switch is allowed to
    // change one field and nothing else.
    expect({ ...after, active: before.active }).toEqual(before);
  });

  it("keeps an absent description absent rather than inventing one", () => {
    const input: EventTypeInput = toEventTypeInput({ ...FULL, description: null });
    expect(input.description).toBeNull();
  });
});
