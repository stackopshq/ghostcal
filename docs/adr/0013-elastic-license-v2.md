# ADR-0013: Elastic License 2.0

## Status

Accepted, 2026-09-25. Supersedes the licensing decision of
[ADR-0001](0001-stack-and-architecture.md).

## Context

GhostCal has been under `AGPL-3.0-or-later` since 2026-06-26, chosen to match an
"open alternative to Calendly" positioning. The suite's commercial position has
since settled on something else, and the whole Ghost suite now has to say the
same thing. GhostPass moved to the Elastic License 2.0 on 2026-08-31
([its ADR-0001](../../../ghostpass/docs/adr/0001-elastic-license-v2.md)); GhostCal
stating a different licence than its siblings is a defect regardless of which one
is right.

Two things have to hold at the same time:

- **The code is public and auditable.** Every product in the suite sells
  zero-knowledge. A claim about what a server cannot decrypt is worth nothing
  unless a reader can go and check it, and unless they can run the thing
  themselves. Closing the source would take the central argument away.
- **Reselling is StackOps' business.** A competitor who takes the source and
  operates it as a paid hosted service captures the revenue without carrying the
  development.

The AGPL does not separate those two. It obliges a competing operator to publish
their modifications — a disclosure duty, not a limit on resale. An operator who
publishes their diff is in full compliance while competing with us on our own
code, which is exactly the outcome the licence was meant to prevent.

## Decision

GhostCal is licensed under the **Elastic License 2.0** (`Elastic-2.0`), effective
2026-09-25. The text in `LICENSE` is Elastic's, reproduced without modification
and byte-identical to `ghostpass/LICENSE` — the suite's reference copy.

The licence permits use, copying, modification, redistribution and self-hosting.
It reserves one thing: providing GhostCal to third parties as a hosted or managed
service. This is *source available*, not open source in the OSI sense, and the
README says so rather than implying otherwise.

## Consequences

- `pyproject.toml` declares `license = "Elastic-2.0"`, a valid SPDX identifier
  (SPDX License List 3.20 and later) and therefore a valid PEP 639 expression.
- **The dependency constraint loosens rather than tightens.** The AGPL required
  dependants to be compatible with a source-disclosure duty; ELv2 imposes none.
  No dependency chosen under the AGPL becomes incompatible by this change.
- **The change is not retroactive**, and does not attempt to be. See `NOTICE`.
  At the time of writing this is a formality: `github.com/stackopshq/ghostcal`
  returns 404, the repository has never been public, and the only contributors
  are Clara Vanacker and Kevin Allioli. No third party holds a copy under the
  AGPL. Saying so in `NOTICE` costs nothing and settles the question in advance.
- **This does not change the App Store export-compliance answer.** The note 3
  exemption of §740.17(b) turns on whether the source is *publicly available*,
  not on the name of the licence — and GhostCal's is not. See
  [`docs/appstore.md`](../appstore.md). The Elastic License 2.0 restricts a *use*
  (managed resale), not redistribution; the BIS question is unaffected either way,
  and remains one for a lawyer.
