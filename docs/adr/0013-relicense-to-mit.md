# 0013: Relicense GhostCal to MIT

*Status: accepted, 2026-08-31*

## Context

ADR-0001 chose AGPL-3.0-or-later for GhostCal, reasoning that network use counts
as distribution and that a source-disclosure obligation matched the
open-alternative positioning Cal.com occupies. That reasoning was sound for a
product considered on its own.

GhostCal is not on its own. It ships as part of the Ghost suite, and every other
product in it is MIT: ghostpass, ghostbit, ghostmon, ghostlink, ghostboard. A
single AGPL component in an otherwise permissive suite is not a stronger
position, it is a trap for whoever integrates the suite: the obligations of the
strictest component effectively govern how the others can be combined and
redistributed, and nobody reads five licence files to discover that.

## Decision

GhostCal is licensed under MIT, with the same copyright line as the rest of the
suite (`Copyright (c) 2026 StackOps HQ`).

**We may do this because StackOps holds all of the copyright.** This is the part
that gates the decision rather than decorating it. MIT is more permissive than
AGPL, so relicensing removes obligations that third parties currently benefit
from, and only the copyright holder can do that. Every commit on `main` was
authored by one of two people, both acting for StackOps: Kevin Allioli, and
Clara Vanacker under four recorded identities (`clara@stackops.ch` under two
surnames, a personal address, and the GitHub `Loutre` alias). No outside
contributor appears in the history, so no third-party consent is required.

Dependencies do not obstruct it either. None of the 17 declared Python
dependencies is under strong copyleft. The frontend lockfile carries
LGPL-3.0-or-later through `sharp`'s prebuilt libvips binaries, which is weak
copyleft: it constrains modification and replacement of that library, not the
licence of the work that calls it.

## Consequences

- Anyone may run a modified GhostCal as a service without offering source. That
  was the point of the AGPL and it is deliberately given up. The suite trades a
  disclosure obligation for being straightforward to adopt.
- The change is not retroactive. Code already distributed under AGPL stays
  available under those terms to whoever received it; MIT applies going forward.
- Adding an outside contributor now makes a future relicence impossible without
  their agreement. Whoever takes the first external contribution should decide
  then whether a CLA or a DCO is wanted, rather than discovering the question
  during the next licence change.
- ghostmail and ghostauth are still AGPL, and are out of scope here. The suite
  is not uniform until they are settled, one way or the other.
