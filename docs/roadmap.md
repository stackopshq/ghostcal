# GhostCal roadmap

GhostCal is a **privacy-first scheduler that became a private calendar** — the agenda layer of the
ghost suite. The through-line is the suite's promise: the server stores ciphertext it can never
read. This roadmap tracks where that promise has reached and where it's going.

## Shipped

### Scheduling core

Pure, property/DST-tested availability engine; booking pages (solo, round-robin, collective,
group); database-guaranteed no-double-booking (`EXCLUDE`); meeting polls; CalDAV busy sync; HMAC
webhooks; analytics. Multi-tenant Postgres RLS throughout. Full UI in EN/FR.
*(see [ADR-0001](adr/0001-stack-and-architecture.md))*

### Zero-knowledge

- **Invitee data.** Invitee name, custom-question answers and notes are sealed in the browser to
  the org public key; the server stores one blob it cannot read. Email/guest emails/meeting links
  are encrypted at rest; only slot times stay cleartext.
  *(see [ADR-0002](adr/0002-zero-knowledge-invitee-data.md))*
- **Team key sharing.** A teammate can decrypt org data: the org key travels in the invitation
  link fragment (`#k=`), never to the server; multi-org unlock at login.
  *(see [ADR-0003](adr/0003-team-zero-knowledge-key-sharing.md))*
- **Crypto stack.** X25519 ECDH + AES-256-GCM (ECIES) + hash-wasm Argon2id on WebCrypto — no
  heavyweight crypto dependency. CSP with `wasm-unsafe-eval`.
- **Security.** Full pentest hardening pass; org invitations are only acceptable by the verified
  owner of the invited email.
- **Self-hosting without weakening the egress guard.** The SSRF guard refuses every private
  address, which is right for a hosted deployment and left self-hosters unable to reach their own
  Nextcloud or Radicale on the LAN. `GHOSTCAL_CALENDAR_ALLOWED_PRIVATE_CIDRS` names ranges to open
  — empty by default, calendars only (never webhooks), and link-local stays refused however it is
  set, so no configuration can expose the cloud-metadata address.
  *(see [ADR-0011](adr/0011-private-network-allow-list-for-self-hosting.md))*

### Private calendar

- **Phase 1 — foundation.** `calendars`/`calendar_events`; a pure DST-correct recurrence engine;
  CRUD + unified agenda (events + bookings + external busy); a month view that seals/decrypts event
  content in-browser. *(see [ADR-0004](adr/0004-zero-knowledge-calendar.md))*
- **Phase 2 — sync & richness.** Event reminders (Celery, time-only); recurrence
  overrides/exceptions (edit/delete one occurrence); external CalDAV event titles in the agenda
  (encrypted at rest, read-only).
- **Phase 3 — shared calendars, read-only or read-write.** Share a calendar with org members, who
  decrypt it with the org key they already hold — so an editor unseals and re-seals exactly as the
  owner does, and the server sees ciphertext either way. Access is a property of the *calendar*, not
  of who created an event on it: that is the only rule under which an event an editor adds to your
  calendar is visible to you. *(see [ADR-0005](adr/0005-shared-calendars.md))*

### Personal calendar client (the Fantastical layer)

The daily-use core of a calendar client, all zero-knowledge unless noted:

- **Natural-language quick-add** (chrono-node, client-side, EN/FR): date, time, duration,
  recurrence, location — sealed in the browser.
- **Month, week and day views** (time grid), with multi-calendar overlays, per-calendar colours and
  visibility toggles.
- **To-do list** with due dates (reusing the quick-add parser) and content-less email reminders.
- **Attendees & RSVP** on personal events: the server stores guest email + status only; the
  organiser's browser supplies the cleartext title to build the ICS at send time, never persisted.
- **Browser notifications** for events and tasks (client-side, so they can show the *decrypted*
  title — unlike the content-less email reminders).
- **Keyboard UX**: command palette (⌘/Ctrl+K) and calendar shortcuts.
- **External calendars as a first-class overlay**: CalDAV events appear coloured and toggleable in
  the personal views, with a "Sync now" action. *Not* zero-knowledge — the server holds the CalDAV
  credentials; an honest, labelled trade-off.
- **Public ICS subscriptions** (fetch → cache) and a **daily weather forecast** in the calendar.
- **Several CalDAV accounts** per member (work + personal + family), each its own coloured overlay.
  Bookings mirror onto exactly one of them — a partial unique index makes "exactly one" true in the
  database, not merely by convention.
- **Five views**: month, week, day, **year** (twelve months, busy days marked — a year has no room
  for titles, and the server could not read them anyway) and **list** ("what is next?", which is the
  question people actually open a calendar to ask).
- **Publish a calendar to CalDAV** — your GhostCal events on your phone, with the server still unable
  to read one. It cannot build the VEVENT, so the browser does: it opens each event and hands the
  cleartext over at push time, and the server relays it and stores none of it. The honest price is
  that a push waits for a browser; a queue makes that liveable.
  *(see [ADR-0008](adr/0008-calendar-publication-without-server-reads.md))*
- **Share a calendar outside the organization**, by secret link — with someone who has no GhostCal
  account at all. The link carries its own keypair; its private half lives in the URL fragment and
  never reaches the server. ADR-0005 had parked this as "grant them the org key", which would have
  handed an outsider the encrypted contents of the *entire organization* to show them one calendar.
  *(see [ADR-0009](adr/0009-sharing-a-calendar-outside-the-organization.md))*

### Suite integration

- **SSO / OIDC login** against GhostAuth (backend + frontend).
- **Ghostboard portal**: a GhostAuth *resource server* on the portal-facing routes only (the app's
  own API keeps its local session), a public `ghostapp.yaml`, and two widgets. They are `stat`
  widgets and will stay `stat` widgets — the server holds event and task titles as ciphertext, so a
  "your next meetings" list is not a widget we chose not to build but one we *cannot* build.
- **GhostMail bridges**, both directions and fully decoupled deep-links (no cross-app backend
  calls, zero-knowledge preserved on both sides): "add to calendar" from a detected date in an
  email → GhostCal quick-add prefill; "email guests" from an event → GhostMail composer.
- **Meeting invitations** (`.ics`) read out of an email and imported exactly. The natural-language
  bridge above *guesses* — and a sentence cannot carry an end time, a location or a recurrence rule,
  so a 90-minute meeting arrived as the default hour. An `.ics` states all three. GhostMail parses
  the attachment in the tab (it is sealed, so only the browser can) and hands the event over through
  a **structured** import link; GhostCal opens the event form, and nothing is saved until the user
  confirms. An invitation email *is* an `.ics`, so this is also how invitations land in the
  calendar — there was never a second feature to build there.
- **Free-busy sharing** (ADR-0010): a link that shows *when* you are busy and never *what* you are
  doing, plus "email it" straight into the GhostMail composer. It needs no sealing at all — busy
  times are already cleartext on the server, because the booking engine has to reason about them —
  so it carries no key and has no fragment, and whoever finds it learns strictly what the server
  already knows.
  Building it is what exposed that the scheduler **could not see your own events**: "Dentist, 14:00"
  in your calendar did not stop a stranger booking you at 14:00. There is now one definition of
  busy, and both the booking page and the free-busy link read it.
- **Ghost-suite app switcher** (Calendar ↔ Mail).

### Account lifecycle

Erasure, portability and storage limitation — the three things a privacy-first product cannot
plausibly ship without. Account deletion (an org you are the sole member of goes with you; in a
shared one you are anonymized out of the records you co-own), data export **assembled in the
browser** (the server holds ciphertext it cannot open, so a server-side export would hand you
base64), and an opt-in booking retention window with a purge job.
*(see [ADR-0006](adr/0006-account-lifecycle-and-erasure.md))*

### Key rotation & revocation

Removing a member used to revoke *nothing*: they kept the org key, and the org's public key never
changed, so everything created **after** they left was still sealed to a key they held. Now each
user has their own keypair, an admin can rotate the org keypair — sealing the new key directly to
every remaining member, who do nothing — and the backlog of already-sealed records is re-sealed in
the browser, batch by batch, resumably. When the backlog reaches zero, the old key opens nothing at
all. *(see [ADR-0007](adr/0007-org-key-rotation-and-revocation.md))*

### Engineering

Ruff + mypy strict; pytest backend suite; Vitest frontend suite; CI (lint, format check, tests,
build, security scan).

## Next

1. **Invitations without a key in the link.** A member who already has an account now receives the
   org key sealed to their public key. A brand-new invitee has no account and therefore no keypair,
   so that case still uses the ADR-0003 fragment grant — and still carries its trade-off. Closing it
   means granting the key only after the invitee has registered. *(see ADR-0007 §5)*
## Later

- **"This calendar counts towards my availability."** Your own events now block your booking page —
  they always should have (see Shipped). But the toggle is all-or-nothing, and not every calendar is
  a claim on your time: an "Anniversaries" calendar should not empty your booking page. The Cal.com
  model is a `blocks_availability` flag per calendar, defaulting to on. Additive, no painful
  migration — worth doing when someone actually complains, and not before.
- **An expiry on shared links.** Neither a calendar link (ADR-0009) nor a free-busy link (ADR-0010)
  ever dies on its own. Revocation is deletion, and that is honest, but "share my availability with
  this recruiter for two weeks" is the normal case and today it means remembering to come back.
- **True two-way CalDAV sync.** Publication is one-way; changes made on the phone come back through
  the busy-sync, not through a reconciliation. A real merge would need the server to read both
  sides — which is exactly what ADR-0008 declines to let it do.

## Debt and traps

Things a newcomer would otherwise rediscover the hard way. None of them is urgent; all of them are
real.

- **`alembic revision --autogenerate` no longer proposes DROPs, and here is why it did.** Half this
  schema is created by hand-written SQL inside migrations — RLS policies, SECURITY DEFINER
  functions, triggers, partial and GiST indexes — and is declared on no model, so autogenerate read
  it as deletable. Unfiltered it proposed dropping the `calendar_event_reminders` table, six indexes
  (including `uq_caldav_one_mirror_per_user`) and three trigger-maintained `updated_at` columns. An
  `include_object` filter in `migrations/env.py` now ignores anything reflected that no model
  claims, so autogenerate is **additive only**. The corollary: removing a model does not generate
  its `DROP` either. Write removals by hand, where the RLS and trigger fallout is visible.
- **CI does not run `tsc --noEmit`.** The frontend job runs eslint, vitest and `next build` — and a
  type error inside a *test* file passes all three. There are two sitting in
  `frontend/src/lib/subscriptions.test.ts` today (a badly typed `fetch` mock). A hole in the feedback
  loop rather than a bug, which is exactly why it stayed.
- **Ghostboard's registry promises a widget we cannot serve.** It declares an "upcoming events"
  **list** widget for ghostcal. Event titles are ciphertext, so the server can serve a *count* and
  never a list. The registry entry is a promise the architecture forbids keeping — fix the registry,
  not the architecture.

## Exploring

- **Desktop shell.** Only worth building for what a browser cannot do: a tray/menubar agenda, a
  **global hotkey** on the existing natural-language quick-add, native notifications when the app is
  closed, launch-at-login, offline. Leaning **Electron over Tauri**: the zero-knowledge layer relies
  on native WebCrypto **X25519**, whose support in system webviews (WebKitGTK, WKWebView) is recent
  and version-dependent, while Electron ships its own Chromium. One shell for the whole suite, not
  one per app. Without the tray + hotkey + notifications trio, a PWA gets most of the value for a
  fraction of the cost.
