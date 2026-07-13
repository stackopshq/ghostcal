# ADR-0009 — Sharing a calendar outside the organization

Status: accepted
Date: 2026-07-13

Supersedes the cross-org note in [ADR-0005](0005-shared-calendars.md).

## Context

ADR-0005 parked this with one sentence:

> **Within-org only.** Sharing with someone outside the organization would require granting them the
> org key — that reuses the invitation-fragment grant (ADR-0003) and is deferred.

**That is not a deferral. It is a trap, and it needs saying out loud before someone acts on it.**

The org key opens:

- `bookings.invitee_private` — every invitee's name, answers and notes, across the whole
  organization;
- `calendar_events.content` — every calendar of every member;
- `tasks.content` — every to-do of every member.

Handing it to an outsider so they can see **one** calendar would hand them the encrypted contents of
the **entire organization**. The shortcut is right there, it reuses machinery that already exists, and
it looks reasonable. It is not.

## Decision

**A link with its own keypair, and the private half in the URL fragment.**

- The link's **public** key is stored server-side. A public key is public.
- The link's **private** key goes into the URL fragment (`/c/<token>#k=<key>`) and stays there.
  Browsers do not transmit fragments. The server has never seen it and never will.
- The owner's browser seals a **copy** of each event's content to the link's public key. The
  org-sealed original stays exactly where it is: this is a second envelope, not a replacement.
- The visitor's browser opens those copies with the key it read out of the fragment.

The server therefore holds two envelopes it cannot open, side by side, and hands one of them to
someone who can. That is the whole design.

This is the suite's signature move — ghostbit does it for pastes, ADR-0003 does it for team key
grants. It is used here for the same reason it is used there: a secret that never reaches the server
is a secret the server cannot lose.

### Why a keypair, and not a shared symmetric key

Because the owner adds events **later**. Sealing a new event to a link needs only the link's *public*
key, and the server already has it. With a symmetric key the owner would have to keep the link's
secret somewhere to keep the calendar current — and "somewhere" is how a secret stops being one.

### Why sealed copies, and not a re-sealed calendar

The events stay sealed to the org key as well. Re-sealing them *to* the link would break every member
of the organization who reads that calendar through the org key. A second envelope costs one row per
(link, event) and breaks nothing.

### What a stale copy is

A lie. When an event changes, every sealed copy of it becomes wrong — so a **trigger deletes them**.
That is what makes them "pending" again, and the owner's browser re-seals them on its next visit.

Until it does, the visitor sees **nothing** for that event rather than its old title. An empty slot
is honest; a wrong one is not.

### What the bargain is

**Whoever has the link has the calendar.** There is no per-person revocation, no audit of who opened
it, no expiry (yet). This is the same bargain ghostbit makes, and it should be stated to the user in
those words rather than implied.

Revocation is deleting the link. Whoever already read it keeps what they read — which is true of
anything anyone has ever been shown, and pretending otherwise would be the lie.

## Consequences

- `calendar_links` (token hash + public key) and `calendar_link_events` (the sealed copies).
- The visitor has no account, no session and no organization, so no RLS context. They get exactly one
  door — a SECURITY DEFINER function taking a token hash — and it leads to one calendar's ciphertext.
- **The fragment must be base64url.** Standard base64 contains `+`, and a fragment parsed with
  `URLSearchParams` decodes `+` as a *space* — so the key comes back corrupted and the failure
  presents as "the link doesn't work". ADR-0003's grant key already learned this; it is written down
  here so the next fragment-carried key does not have to learn it again.
- Minting a link shares nothing on its own: the copies do not exist yet, and only the owner's browser
  can make them. The count of what is left to seal is surfaced, so a half-made link does not look
  like a broken one.
- Read-only. A visitor with no account and no org has nothing to write with.
