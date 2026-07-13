# ADR-0008 — Publishing a calendar to CalDAV, without the server reading an event

Status: accepted
Date: 2026-07-13

## Context

GhostCal reads external calendars (ADR-0004 onwards) and writes *bookings* back to one of them
(`mirror.py`). What it could not do is put your **own** GhostCal events on your phone — which is a
strange gap for something claiming to be a calendar client.

The obstacle is the product's whole point. A CalDAV server needs a `VEVENT` with a `SUMMARY`, a
`LOCATION`, a `DESCRIPTION`. GhostCal's server holds those sealed to an organization key it does not
have. It cannot build that VEVENT. Not "does not"; **cannot**.

So there is no version of this feature that does not decide something about zero-knowledge, and the
decision should be made in the open rather than discovered later in a diff.

## Options

**Server-side sync.** Mark a calendar "synced"; store its events in a form the server can read
(encrypted at rest, like CalDAV credentials); let the worker push and pull on a schedule.

This is what every other calendar app does, and it is the only way to get true background two-way
sync. It is also, precisely and irreversibly, the end of zero-knowledge for those calendars. The
precedent exists — external CalDAV events are already server-readable (a labelled trade-off) — but
those are events *somebody else's server already has*. These would be ours, given away.

**Browser relay.** The browser holds the key, so the browser opens the event and hands the cleartext
to the server at push time. The server forwards it to the CalDAV server and stores none of it.

## Decision

**Browser relay.** The server relays cleartext; it never stores it.

This is not a new pattern in this codebase — it is the one event invitations already use. From
`send_event_invitation_email`: *"we only relay the invitation email built from browser-supplied
cleartext (never persisted)"*. The same shape, for the same reason, with the same guarantee.

### The cost, stated plainly

**A push waits for a browser.** There is no worker doing this on a schedule, because a worker cannot
read an event. There is no background reconciliation, for the same reason.

This is the honest price of the guarantee, and it should be said in the UI rather than buried here.

### Why a queue

Not to be clever — because deletes force it. Once an event row is gone there is nothing left to mark
as needing a push, so the operation has to outlive the thing it refers to. Hence a queue keyed on a
**deterministic UID** (`ghostcal-evt-<event_id>`), which survives the row.

The queue also means the tab does not have to be open *at the moment of the change* — only at some
moment afterwards. That turns "publishing requires a browser" from a crippling constraint into a
tolerable one.

The queue is filled by a **trigger** on `calendar_events`, not by the application: every write path
gets it, including the ones written later by someone who never read this file. (The same argument as
the seal-generation stamp in ADR-0007.)

### What the queue does not contain

No summary, no location, no description. It holds a UID, an operation, and a pointer at a sealed
event. A test asserts the column list, because "we don't store cleartext" is the kind of claim that
quietly stops being true.

### Failure

A queue row is dropped only **after** its CalDAV write lands. A stale password or an unreachable
server leaves the change queued, to be tried again — which is the entire point of having a queue
rather than a fire-and-forget.

## Consequences

- `calendars.push_connection_id` — which connected CalDAV calendar this one publishes to. NULL is
  the default, and the default is: nothing leaves.
- Turning publication *on* backfills: a calendar that only publishes its future is not published.
- Recurring events publish their `RRULE`. Without it a weekly event lands on the phone once and never
  again — worse than not publishing, because it looks right.
- The cleartext exists in the API process for the duration of one CalDAV request. It is not logged,
  not cached, not written. That is a property of the code, and only tests keep it one.
- Two-way sync is still one-way-plus-read: changes made on the phone come back through the existing
  busy-sync, not through a reconciliation. A real merge would need the server to read both sides.
