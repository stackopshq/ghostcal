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
- **Phase 3 — shared calendars.** Share a calendar with org members, who decrypt it with the org
  key they already hold; a sharing/ACL model + agenda inclusion, read-only. The zero-knowledge
  property holds. *(see [ADR-0005](adr/0005-shared-calendars.md))*

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

### Suite integration

- **SSO / OIDC login** against GhostAuth (backend + frontend).
- **GhostMail bridges**, both directions and fully decoupled deep-links (no cross-app backend
  calls, zero-knowledge preserved on both sides): "add to calendar" from a detected date in an
  email → GhostCal quick-add prefill; "email guests" from an event → GhostMail composer.
- **Ghost-suite app switcher** (Calendar ↔ Mail).

### Engineering

Ruff + mypy strict; pytest backend suite; Vitest frontend suite; CI (lint, format check, tests,
build, security scan).

## Next

Ordered. The first two close gaps in promises the product already makes — they come before any new
feature.

1. **Account lifecycle / GDPR.** Account deletion (cascade across the RLS tables), data export
   (JSON + ICS), booking retention and auto-purge. A privacy-first product cannot ship publicly
   without the right to erasure and portability.
2. **Key rotation & revocation.** Today the org private key is cached by every member who ever
   received it, so removing a member from the org revokes *nothing* — they can still decrypt.
   Rotate the org keypair, re-seal existing data, and re-distribute to the remaining members. This
   is a hole in the zero-knowledge promise itself, not a convenience.
3. **Ghostboard portal integration.** GhostCal has SSO login but is not yet a GhostAuth *resource
   server*: it accepts no GhostAuth access token on its API and serves no `ghostapp.yaml` or widget
   `data_url`, so its portal widget stays hidden. Note the zero-knowledge constraint — the server
   cannot read sealed events, so the widget can only ever be a **count**, never a list of titles.

## Later

- **Multiple external accounts.** `CaldavConnection` is still one per user; a calendar client needs
  several (work + personal + iCloud).
- **Year and agenda-list views.** Month/week/day exist; the remaining two Fantastical views do not.
- **Calendar push & cross-org sharing.** Optional non-ZK **synced** calendars that push to a
  third-party CalDAV server (clearly labelled — booking write-back already exists); read-write
  shared calendars; sharing beyond the org via the invitation-fragment grant.
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
