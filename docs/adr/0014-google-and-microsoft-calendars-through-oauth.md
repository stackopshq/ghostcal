# 0014 — Google and Microsoft calendars, read and write, through OAuth

*Status: accepted — 2026-10-22*

## Context

A host can connect an external calendar so GhostCal reads its busy time and
writes bookings back to it (the mirror, `application/mirror.py`). Both run over
CalDAV with a username and an app password (`caldav_connections`).

Google and Microsoft, the two calendars most hosts actually use, cannot be
connected that way:

- **Google** serves CalDAV only behind OAuth 2.0; no app password opens it.
- **Microsoft** answers no CalDAV discovery record (measured 2026-08-31, see
  `frontend/src/lib/caldavProviders.ts`); its calendars are reached through
  Microsoft Graph.

So both are available today only as an `.ics` subscription: read-only, polled,
no write-back. Bookings never reach the calendar the host actually looks at, and
a cancelled booking cannot be removed from it.

`caldavProviders.ts` records why Google was closed: Google accepts no wildcard
in an OAuth redirect URI, so a client registered by StackOps cannot redirect
back to a self-hoster's own domain. That objection is about **self-hosting**.
The hosted deployment, `cal.ghostsuite.cloud`, has one fixed origin, and one
registered redirect URI serves it.

## Decision

Connect Google Calendar and Microsoft 365 / Outlook.com through **their own
APIs**, authorised with **OAuth 2.0 authorization code + PKCE**, read and write.

**Scope of deployments.** The hosted deployment registers one client per
provider. A self-hosted deployment gets the feature only if its operator
registers their own client and sets its id and secret; otherwise the providers
stay "not connectable", as today. No relay is hosted for self-hosters: it would
see every authorization code and take the self-hosted out of self-hosted.

**Least privilege.**

| Provider  | Scopes                                                                 | Class                   |
|-----------|------------------------------------------------------------------------|-------------------------|
| Google    | `calendar.events`, `calendar.calendarlist.readonly`                    | sensitive (not restricted) |
| Microsoft | `Calendars.ReadWrite`, `offline_access` (delegated, multi-tenant app)  | user-consentable        |

No mail, contacts or drive scope. The full `calendar` scope is not requested.

**Same port, new adapters.** `GoogleCalendarClient` and `GraphCalendarClient`
implement the existing `CalendarClient` protocol (`list_calendars`,
`fetch_busy`, `create_event`, `delete_event`). The mirror, `mirror_detail`
redaction and the busy sync stay provider-agnostic: what leaves the product is
still decided in `mirror.py` and nowhere else.

**Storage.**

- `caldav_connections` gains `provider` (`caldav` | `google` | `microsoft`).
  OAuth connections store a refresh token, encrypted with the same `SecretBox`
  as CalDAV passwords; no access token is persisted.
- The remote event id returned on creation is stored with the mirrored booking.
  Neither API deletes by iCalendar UID, and the CalDAV cancel bug of
  2026-10-16 came from deleting by a search that could miss.

**Failure is visible.** A refresh refused with `invalid_grant` (password
change, consent withdrawn, token expired) sets the connection to
`reauth_required`, shown in the calendar list with a reconnect action. The
booking still succeeds; only the mirror is skipped, as today.

**Disconnecting** deletes the refresh token and, for Google, calls the token
revocation endpoint. Graph has no per-token revocation; the account page links
to where the user withdraws consent.

**Sync stays polled** by the existing `sync_all_calendars` beat task. Push
notifications (Google watch channels, Graph subscriptions) need a public
callback and renewal jobs; they are a later optimisation, not a prerequisite.

**Order.** Microsoft first: an Entra app works with a test tenant on day one.
Google's verification of the sensitive scope runs in parallel; until it is
granted the Google client is limited to 100 test users and shows the
unverified-app warning, so it is not offered to customers before then.

## Consequences

- **Registration work outside the code.**
  - Google: OAuth consent screen, verified domain, published privacy policy and
    a demonstration video for verification. The policy must state compliance
    with the Google API Services User Data Policy, Limited Use included.
  - Microsoft: Entra multi-tenant app, publisher verification (Microsoft
    partner account) to remove the "unverified publisher" warning. Some
    customer tenants will still require their admin's consent.
- **Two more processors.** Booking data (subject to `mirror_detail`) reaches
  Google and Microsoft at the host's request. That goes into the GDPR/nLPD
  record of processing and the privacy policy, as iCloud already should.
- **Secrets.** Client ids and secrets live in OpenBao and are rendered by the
  deployment role, like the other `GHOSTCAL_*` secrets. A leaked client secret
  is rotated at the provider; the refresh tokens survive it.
- **Two more APIs to keep up with**, each with its own quotas, error shapes and
  deprecations. CalDAV stays for everything else (iCloud, Fastmail, Nextcloud,
  Infomaniak).
- **`caldavProviders.ts` changes meaning**: Google and Microsoft move from
  "not connectable" to "connect with Google / Microsoft" on the hosted
  deployment. Its comment on the wildcard stays true for self-hosting and must
  say so, so nobody reopens the question for the wrong deployment.

## Alternatives rejected

- **Keep `.ics` subscriptions only.** Read-only by nature: it is the problem.
- **Google CalDAV with OAuth.** Same OAuth registration and verification, for a
  protocol Google maintains less than its API, and no Microsoft equivalent.
- **A hosted OAuth relay for self-hosters.** Sees every self-hoster's
  authorization code; rejected for the reason above.
- **A third-party unified calendar API (Nylas, Cronofy).** One more processor
  holding every host's tokens, priced per account, for two integrations.
