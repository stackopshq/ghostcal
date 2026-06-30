# ADR-0005: Shared calendars

- Status: Accepted
- Date: 2026-06-30

## Context

Calendar Phase 3 ([ADR-0004](0004-zero-knowledge-calendar.md)): let a user share a calendar with
others so they can see its events. The events are **zero-knowledge** — sealed to the organization
public key (ADR-0002). The challenge "how does another user decrypt them" is already solved:
**team key sharing ([ADR-0003](0003-team-zero-knowledge-key-sharing.md)) gives every org member the
org key**. So a member can already open any event sealed to their org — sharing is an
**authorization** problem, not a cryptography one.

## Decision

**Within-organization, read-only calendar sharing.**

- A new `calendar_shares` table maps `(calendar_id → shared_with_user_id)`, org-scoped under RLS,
  unique per pair. (`can_edit` is reserved for a future read-write mode; Phase 3 is read-only.)
- Only the calendar's **owner** may share/unshare it.
- `list_calendars` returns the user's own calendars **plus** calendars shared with them (flagged,
  with the owner's name). The agenda includes events from shared calendars; those agenda items are
  marked **read-only** so the UI shows but does not edit them.
- The sharee decrypts the events with the org key they already hold — **no new crypto, no
  re-sealing, the zero-knowledge property is unchanged** (the server still can't read the content).

## Consequences

- **Sharing is pure authorization** (an ACL row + an OR-clause in the agenda query). The crypto
  story is untouched.
- **Read-only first.** Editing a shared event is the owner's prerogative; collaborative editing
  (`can_edit`) is a later iteration (it needs conflict handling and per-event permissions).
- **Within-org only.** Sharing with someone outside the organization would require granting them
  the org key — that reuses the invitation-fragment grant (ADR-0003) and is deferred.
- **Revocation is immediate for new reads** (the share row is gone) but, like all org-key access,
  is not retroactive against a cached key — the standing org-key-rotation caveat applies.
- The agenda's "owner_id == me" filter becomes "mine OR in a calendar shared with me"; RLS still
  guarantees same-org isolation.
