# ADR-0004: Zero-knowledge personal calendar

- Status: Accepted
- Date: 2026-06-30

## Context

GhostCal began as a Calendly-style scheduler (booking pages over an availability engine). The
product direction is to also be a **calendar** — a place to keep your own events — in preparation
for **ghostmail** (a private email tool that needs a private agenda: "add to calendar", invites,
free-busy). Today the model has booking-page configs (`event_types`), invitee-driven `bookings`,
projected CalDAV busy (`external_busy`) and a CalDAV sync — but no notion of a user's **own**
events or calendars.

A plain calendar clone (Google Calendar) has no reason to exist in this suite. Like the rest of
GhostCal, its reason is **privacy**: the server should schedule and compute free-busy on times it
can read, but must not be able to read **what** your events are.

## Decision

Add a **zero-knowledge personal calendar**, reusing the organization keypair from
[ADR-0002](0002-zero-knowledge-invitee-data.md)/[ADR-0003](0003-team-zero-knowledge-key-sharing.md).

**Data model (new, alongside the scheduling tables — bookings are untouched):**

- `calendars` — a user's calendar collections: `id, organization_id, owner_id, name, color,
  is_default`.
- `calendar_events` — the user's own events: `id, organization_id, owner_id, calendar_id`,
  **cleartext** scheduling fields `start_at, end_at, all_day, timezone, rrule (RFC 5545), exdates`,
  `status`, and a **single sealed blob** `content` holding `{ title, description, location }` —
  encrypted to the org public key (ECIES, ADR-0002), decrypted only in the browser.

**The boundary mirrors ADR-0002's tiers:**

- 🔒 **Zero-knowledge:** event title, description, location — the server never reads them.
- ⏱️ **Cleartext:** start/end/all-day/timezone/rrule — needed to expand occurrences, compute
  free-busy, schedule reminders, and answer "are you busy at 3pm" without learning *why*.

**Domain — a pure recurrence engine** (sibling of the availability engine): expand an event's
`rrule`/`exdates` into concrete occurrences within a `[from, to]` window, DST-correct, no I/O —
exhaustively property-testable.

**Read model — a unified agenda** endpoint that, over a date range, unions: expanded
`calendar_events` (with their sealed `content`) + confirmed `bookings` + `external_busy`. Times are
cleartext; the browser decrypts event content and shows a month/week/day view.

**Interop:** iCalendar (`.ics`) import/export so events flow to/from ghostmail and other clients.
Import decrypts/encrypts client-side; export is a client-side build from decrypted content.

## Consequences

- **GhostCal becomes a private calendar**, not just a scheduler — a real differentiator versus
  Google/Microsoft and the natural agenda for ghostmail.
- **Reuses the existing ZK stack** (org keypair, `e2e.ts`, unlock-on-login): event content is just
  another sealed blob. No new crypto.
- **Server-side reminders for events can't name the event** (same tradeoff as booking reminders):
  "You have an event at 15:00 — open GhostCal for details." Accepted.
- **Recurrence is the hard part**, as timezones were for scheduling. It gets the same treatment: a
  pure engine with golden DST cases and property tests. `python-dateutil` expands RRULEs; overrides
  and EXDATE are first-class.
- **CalDAV for personal events** (writing your events to an external server, reading external
  events as a layer) is deferred to Phase 2 — content sent to a third-party CalDAV server is no
  longer zero-knowledge, so it is opt-in and clearly labelled.
- **Bookings stay separate** from `calendar_events` (different lifecycle, invitee ZK, EXCLUDE
  constraint); the agenda unions them at read time rather than forcing one table.

## Delivery plan

- **Phase 1 — foundation (this ADR's scope to implement):** `calendars` + `calendar_events`
  (RLS, ZK content); the recurrence-expansion domain engine + property/DST tests; CRUD for
  calendars and events; the unified agenda read endpoint; a minimal `/dashboard/calendar`
  month view with create/edit, decrypting content in-browser.
- **Phase 2 — sync & richness:** CalDAV bidirectional for personal events (opt-in, non-ZK to the
  external server); recurring-occurrence overrides/exceptions; event reminders (Celery).
- **Phase 3 — ghostmail hooks:** `.ics` import from email, "add to calendar", free-busy sharing,
  meeting invitations that land in the recipient's GhostCal calendar.
