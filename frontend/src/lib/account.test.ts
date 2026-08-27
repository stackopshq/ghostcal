import { beforeEach, describe, expect, it, vi } from "vitest";
import { type AccountExport, buildIcs, openExport } from "@/lib/account";
import {
  generateKeyMaterial,
  sealContent,
  sealTaskContent,
  storeUnlockedKey,
} from "@/lib/zk";
import { clearUnlockedKeys, unlockWithPassword } from "@/lib/zk";

// The export is assembled in the browser precisely because the server cannot open these blobs
// (ADR-0006 §5). So the tests here seal with a real key, then check the archive comes out readable —
// and, just as importantly, that a blob we hold no key for leaves a visible hole rather than
// vanishing.

const ORG_A = "11111111-1111-1111-1111-111111111111";
const ORG_B = "22222222-2222-2222-2222-222222222222";
const PASSWORD = "correct horse battery staple";
const RECOVERY = "aaaa-bbbb-cccc-dddd";

/** Generate a real org keypair, unlock it as login does, and hand back the public key to seal with. */
async function unlockedOrg(orgId: string): Promise<string> {
  const material = await generateKeyMaterial(PASSWORD, RECOVERY);
  const privateKey = await unlockWithPassword(
    PASSWORD,
    material.wrapped_private_key,
    material.wrap_salt,
  );
  storeUnlockedKey(orgId, { publicKey: material.public_key, privateKey });
  return material.public_key;
}

function emptyExport(): AccountExport {
  return {
    profile: {
      id: "u1",
      email: "kevin@example.com",
      name: "Kevin",
      timezone: "Europe/Zurich",
      email_verified_at: null,
      created_at: "2026-01-01T00:00:00Z",
    },
    organizations: [],
    calendars: [],
    tasks: [],
    bookings: [],
    event_types: [],
    schedules: [],
    subscriptions: [],
    caldav_connections: [],
  };
}

describe("openExport", () => {
  beforeEach(() => {
    clearUnlockedKeys();
  });

  it("unseals event and task content with the org key the browser holds", async () => {
    const publicKey = await unlockedOrg(ORG_A);
    const raw = emptyExport();
    raw.calendars = [
      {
        id: "c1",
        organization_id: ORG_A,
        name: "Personal",
        color: "#00f0ff",
        is_default: true,
        events: [
          {
            id: "e1",
            calendar_id: "c1",
            start_at: "2026-06-01T10:00:00Z",
            end_at: "2026-06-01T11:00:00Z",
            all_day: false,
            timezone: "Europe/Zurich",
            rrule: null,
            exdates: [],
            status: "confirmed",
            reminder_minutes: null,
            content_sealed: await sealContent(
              {
                title: "Dentist",
                description: "bring the X-ray",
                location: "Rue du Rhône",
              },
              publicKey,
            ),
          },
        ],
      },
    ];
    raw.tasks = [
      {
        id: "t1",
        organization_id: ORG_A,
        due_at: null,
        completed: false,
        completed_at: null,
        reminder_minutes: null,
        content_sealed: await sealTaskContent(
          { title: "Renew passport", notes: "" },
          publicKey,
        ),
      },
    ];

    const opened = await openExport(raw);

    expect(opened.calendars[0].events[0].content?.title).toBe("Dentist");
    expect(opened.calendars[0].events[0].content?.location).toBe(
      "Rue du Rhône",
    );
    expect(opened.tasks[0].content?.title).toBe("Renew passport");
    expect(opened.unopened).toBe(0);
  });

  it("counts blobs it cannot open instead of dropping the record", async () => {
    // Sealed to org B, but only org A's key is unlocked: the record must survive as a hole.
    const publicKeyB = await unlockedOrg(ORG_B);
    clearUnlockedKeys();
    await unlockedOrg(ORG_A);

    const raw = emptyExport();
    raw.tasks = [
      {
        id: "t1",
        organization_id: ORG_B,
        due_at: null,
        completed: false,
        completed_at: null,
        reminder_minutes: null,
        content_sealed: await sealTaskContent(
          { title: "Secret", notes: "" },
          publicKeyB,
        ),
      },
    ];

    const opened = await openExport(raw);

    expect(opened.tasks).toHaveLength(1); // the record is still there…
    expect(opened.tasks[0].content).toBeNull(); // …with a visible hole, not silently gone
    expect(opened.unopened).toBe(1);
  });

  it("leaves nothing to open when there is nothing sealed", async () => {
    const opened = await openExport(emptyExport());
    expect(opened.unopened).toBe(0);
  });
});

describe("buildIcs", () => {
  beforeEach(() => {
    clearUnlockedKeys();
  });

  it("writes decrypted events any calendar app can read, and escapes ICS metacharacters", async () => {
    const publicKey = await unlockedOrg(ORG_A);
    const raw = emptyExport();
    raw.calendars = [
      {
        id: "c1",
        organization_id: ORG_A,
        name: "Personal",
        color: "#00f0ff",
        is_default: true,
        events: [
          {
            id: "e1",
            calendar_id: "c1",
            start_at: "2026-06-01T10:00:00Z",
            end_at: "2026-06-01T11:00:00Z",
            all_day: false,
            timezone: "UTC",
            rrule: "FREQ=WEEKLY;BYDAY=MO",
            exdates: [],
            status: "confirmed",
            reminder_minutes: null,
            content_sealed: await sealContent(
              {
                title: "Lunch, with Sam",
                description: "",
                location: "Café; Lumen",
              },
              publicKey,
            ),
          },
        ],
      },
    ];

    const ics = buildIcs(await openExport(raw));

    expect(ics).toContain("BEGIN:VCALENDAR");
    expect(ics).toContain("DTSTART:20260601T100000Z");
    expect(ics).toContain("DTEND:20260601T110000Z");
    expect(ics).toContain("RRULE:FREQ=WEEKLY;BYDAY=MO");
    // Commas and semicolons are ICS field separators — unescaped, they would corrupt the file.
    expect(ics).toContain("SUMMARY:Lunch\\, with Sam");
    expect(ics).toContain("LOCATION:Café\\; Lumen");
    expect(ics.endsWith("END:VCALENDAR")).toBe(true);
  });

  it("keeps an unopenable event in the calendar, marked as encrypted", async () => {
    const publicKeyB = await unlockedOrg(ORG_B);
    clearUnlockedKeys(); // no key at all now

    const raw = emptyExport();
    raw.calendars = [
      {
        id: "c1",
        organization_id: ORG_B,
        name: "Work",
        color: "#00f0ff",
        is_default: false,
        events: [
          {
            id: "e1",
            calendar_id: "c1",
            start_at: "2026-06-01T10:00:00Z",
            end_at: "2026-06-01T11:00:00Z",
            all_day: false,
            timezone: "UTC",
            rrule: null,
            exdates: [],
            status: "confirmed",
            reminder_minutes: null,
            content_sealed: await sealContent(
              { title: "Secret", description: "", location: "" },
              publicKeyB,
            ),
          },
        ],
      },
    ];

    const ics = buildIcs(await openExport(raw));

    expect(ics).toContain("BEGIN:VEVENT");
    expect(ics).toContain("SUMMARY:(encrypted, key locked)");
    expect(ics).not.toContain("Secret");
  });
});

vi.mock("@/lib/auth", () => ({ authedFetch: vi.fn() }));
