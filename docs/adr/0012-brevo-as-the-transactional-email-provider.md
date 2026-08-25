# 0012 — Brevo as a transactional email provider, alongside Resend

*Status: accepted — 2026-08-25*

## Context

GhostCal writes to people who are not its users: invitees receiving a booking
confirmation, hosts receiving a notice. That mail has to arrive, and arriving is
not a property of the application — it is a property of the sending domain.

Until now the only adapter was Resend, with a logging fallback:

```
build_email_sender() -> ResendEmailSender if resend_api_key
                        LogEmailSender    otherwise
```

Two things made this insufficient for the deployment that runs the product.

**The sending domain is authenticated with a different provider.** `stackops.ch`
publishes DKIM records for Brevo and lists Brevo in its SPF, and it runs DMARC
`p=reject`. Under `p=reject`, a message that no provider has signed *for that
domain* is refused by the receiving server — not filed as junk, refused. So the
provider is not an interchangeable detail behind a key: it has to be the one the
domain vouches for.

**The fallback is silent.** `LogEmailSender` is the right behaviour in
development and a silent outage in production: the request succeeds, the booking
appears, and nobody learns that the confirmation went to a log file. That is how
this gap survived — an operator role rendered five `GHOSTCAL_SMTP_*` variables
and asserted on an SMTP password for weeks, against an image that has never had
an SMTP branch. Nothing read them, and nothing said so.

## Decision

Add `BrevoEmailSender`, using Brevo's HTTP API, and prefer it when
`GHOSTCAL_BREVO_API_KEY` is set. Resend stays as-is for deployments that use it;
with neither key, the logging fallback stays, and now names both providers.

**The HTTP API, not Brevo's SMTP relay.** GhostCal is deployed on customer
machines whose egress address is not known in advance and changes. A relay that
authorises by IP allow-list cannot follow that; a key posted from anywhere can.
This is the same reason the Google Workspace relay — which authorises by IP —
serves the internal tooling and not the product.

The adapter carries the provider's shape rather than translating it: `sender` is
a structured object where Resend takes the RFC 5322 string, the body field is
`htmlContent`, and attachments live under `attachment`, singular, keyed by `name`.
The shared `email_from` setting is therefore parsed for this provider and passed
through untouched for the other.

## Consequences

- `email_from` and the provider choice are coupled. An address on a domain the
  active provider is not authenticated for will be rejected outright when that
  domain runs `p=reject`. This is worth stating because the two settings look
  independent.
- Preference order is pinned by tests, not by a comment. The estate has already
  been burned by a comment describing a code path that did not exist.
- The logging fallback remains reachable in production. Making it fatal is a
  separate decision: it would trade a silent failure for a refusal to start, and
  that is only an improvement once every deployment has a key.
