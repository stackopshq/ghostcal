# GhostCal roadmap

GhostCal is a **privacy-first scheduler that became a private calendar** — the agenda layer of the
ghost suite. The through-line is the suite's promise: the server stores ciphertext it can never
read. This roadmap tracks where that promise has reached and where it's going.

## Shipped

### Scheduling core

Pure, property/DST-tested availability engine; booking pages (solo, round-robin, collective,
group); database-guaranteed no-double-booking (`EXCLUDE`); meeting polls; CalDAV busy sync; HMAC
webhooks; analytics. Multi-tenant Postgres RLS throughout. Full UI in EN/FR/ES.
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

- **Natural-language quick-add** (chrono-node, client-side, EN/FR/ES): date, time, duration,
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

### Suite integration

- **SSO / OIDC login** against GhostAuth (backend + frontend).
- **Ghostboard portal**: a GhostAuth *resource server* on the portal-facing routes only (the app's
  own API keeps its local session), a public `ghostapp.yaml`, and two widgets. They are `stat`
  widgets and will stay `stat` widgets — the server holds event and task titles as ciphertext, so a
  "your next meetings" list is not a widget we chose not to build but one we *cannot* build.
- **GhostMail bridges**, both directions and fully decoupled deep-links (no cross-app backend
  calls, zero-knowledge preserved on both sides): "add to calendar" from a detected date in an
  email → GhostCal quick-add prefill; "email guests" from an event → GhostMail composer.
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
2. **Self-hosted CalDAV is unreachable, by design.** The SSRF guard (`assert_public_url`) refuses
   loopback *and every private range*. That is the right posture for a hosted deployment. But
   GhostCal is self-hostable, and a self-hoster's Nextcloud or Radicale lives on their LAN at
   `192.168.x.x` — so they can never connect their own calendar. Not a bug; a real tension between
   SSRF protection and self-hosting. An opt-in allow-list of private CIDRs would resolve it, and
   weakening a security control is a decision, not something to slip into a feature branch.

## Later

- **Calendar push & cross-org sharing.** Optional non-ZK **synced** calendars that push to a
  third-party CalDAV server (clearly labelled — booking write-back already exists); sharing beyond
  the org via the invitation-fragment grant.
- **Remaining ghostmail hooks.** `.ics` import from an email, free-busy sharing, and meeting
  invitations that land directly in the recipient's GhostCal calendar.

## Exploring

- **Desktop shell.** Only worth building for what a browser cannot do: a tray/menubar agenda, a
  **global hotkey** on the existing natural-language quick-add, native notifications when the app is
  closed, launch-at-login, offline. Leaning **Electron over Tauri**: the zero-knowledge layer relies
  on native WebCrypto **X25519**, whose support in system webviews (WebKitGTK, WKWebView) is recent
  and version-dependent, while Electron ships its own Chromium. One shell for the whole suite, not
  one per app. Without the tray + hotkey + notifications trio, a PWA gets most of the value for a
  fraction of the cost.
