# GhostCal roadmap

GhostCal is a **privacy-first scheduler that's becoming a private calendar** — the agenda layer for
ghostmail. The through-line is the ghost suite's promise: the server stores ciphertext it can never
read. This roadmap tracks where that promise has reached and where it's going.

## Shipped

- **Scheduling core.** Pure, property/DST-tested availability engine; booking pages (solo,
  round-robin, collective, group); database-guaranteed no-double-booking (`EXCLUDE`); meeting
  polls; CalDAV busy sync; HMAC webhooks; analytics. Multi-tenant Postgres RLS throughout. *(see
  [ADR-0001](adr/0001-stack-and-architecture.md))*
- **Zero-knowledge invitee data.** Invitee name, custom-question answers and notes are sealed in
  the browser to the org public key; the server stores one blob it cannot read. Email/guest
  emails/meeting links are encrypted at rest; only slot times stay cleartext. *(see
  [ADR-0002](adr/0002-zero-knowledge-invitee-data.md))*
- **Team key sharing.** A teammate can decrypt org data: the org key travels in the invitation
  link fragment (`#k=`), never to the server; multi-org unlock at login. *(see
  [ADR-0003](adr/0003-team-zero-knowledge-key-sharing.md))*
- **Vendored WebCrypto crypto stack.** X25519 ECDH + AES-256-GCM (ECIES) + hash-wasm Argon2id —
  no heavyweight crypto dependency. CSP with `wasm-unsafe-eval`.
- **Zero-knowledge calendar — Phase 1.** `calendars`/`calendar_events`; a pure DST-correct
  recurrence engine; CRUD + unified agenda (events + bookings + external busy); a month view that
  seals/decrypts event content in-browser. *(see [ADR-0004](adr/0004-zero-knowledge-calendar.md))*
- **Calendar Phase 2 — sync & richness.** Event reminders (Celery, time-only); recurrence
  overrides/exceptions (edit/delete one occurrence); external CalDAV event titles in the agenda
  (encrypted at rest, read-only).
- **Calendar Phase 3 — shared calendars.** Share a calendar with org members who decrypt it with
  the org key they already hold (team key sharing); a sharing/ACL model + agenda inclusion,
  read-only. The zero-knowledge property holds. *(see [ADR-0005](adr/0005-shared-calendars.md))*

## Next

- **Calendar push & cross-org sharing.** Optional non-ZK **synced** calendars that push to a
  third-party CalDAV server (clearly labelled); read-write shared calendars; sharing beyond the org
  via the invitation-fragment grant.

## Later

- **ghostmail hooks.** `.ics` import from email, "add to calendar", free-busy sharing, and meeting
  invitations that land directly in the recipient's GhostCal calendar — making GhostCal the private
  agenda behind ghostmail.
- **Account lifecycle / GDPR.** Account deletion, data export, booking retention/auto-purge.
- **Key rotation & revocation.** Rotate an org keypair (re-seal) to truly revoke a removed member's
  cached access.
