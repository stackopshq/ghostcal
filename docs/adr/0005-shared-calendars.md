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


## Addendum (2026-07-13): read-write sharing

`can_edit` is now real. A share is granted read-only or read-write, and the owner can move it either
way — re-sharing upserts, so a downgrade takes effect rather than silently doing nothing.

The crypto story is still untouched, and for the same reason as before: both parties are members of
the same organization and already hold the org key, so an editor unseals and re-seals exactly as the
owner does. The server sees ciphertext whichever way the grant points.

**What did change is the access model, and it had to.** Visibility was keyed on *who created an
event* ("events I own, plus calendars shared with me"). That rule collapses the moment an editor can
add an event to someone else's calendar: the event would be owned by the editor and live on the
owner's calendar, so the **owner would not see it** — not created by them, and their own calendar is
not "shared with" them. It would sit on their calendar and they would never know.

So access is now a property of the **calendar**:

- **visible** = events on calendars you own, plus every calendar shared with you;
- **writable** = calendars you own, plus those shared with you *for editing*;
- `read_only` on an event = its calendar is not writable by the viewer.

The event's `owner_id` stays as "who created it" — reminders still go to them, which is right: the
person who put a thing in a calendar is the person who wants to be reminded of it.

**A hole this exposed.** Nothing had ever checked that the calendar an event is created on belongs to
the caller: the calendar id came straight off the request, and RLS scopes writes to the organization
and stops there. A colleague could put an event on your calendar — and under the owner-keyed rule you
would not even have seen it. `create_event`/`update_event` now refuse (403) unless the target
calendar is writable by the caller.
