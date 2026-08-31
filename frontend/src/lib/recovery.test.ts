/**
 * A reset must say what it cannot reopen, before the user commits.
 *
 * An org key reaches a member two ways: wrapped under their password — and, generated at the same
 * moment, under their recovery phrase — or **sealed to their user keypair**, which is how a rotated
 * organisation hands out a new generation. Only the first kind has a recovery envelope; the user
 * keypair has none at all, on purpose (ADR-0003: a lost keypair is re-granted, not recovered).
 *
 * So a reset reopens some generations and not others, and the difference is invisible afterwards: a
 * calendar missing half its entries looks exactly like a calendar someone deleted from. The screen
 * has to name the gap in advance, which means the decision has to be a function something can test.
 */

import { describe, expect, it } from "vitest";

import { isRecoverable, outlookFor, type ResetBundle } from "@/lib/recovery";

function bundle(over: Partial<ResetBundle> = {}): ResetBundle {
  return {
    organization_id: "11111111-2222-4333-8444-555555555555",
    public_key: "cHVibGlj",
    generation: 0,
    sealed_org_key: null,
    wrapped_private_key: "d3JhcHBlZA==",
    wrap_salt: "c2FsdA==",
    recovery_wrapped_private_key: "cmVjb3Zlcnk=",
    recovery_salt: "cmVjb3Zlcnktc2FsdA==",
    ...over,
  };
}

/** A generation handed out by a rotation: sealed to the keypair, no recovery copy anywhere. */
const granted = bundle({
  generation: 1,
  sealed_org_key: "c2VhbGVk",
  wrapped_private_key: null,
  wrap_salt: null,
  recovery_wrapped_private_key: null,
  recovery_salt: null,
});

describe("outlookFor", () => {
  it("separates what the phrase opens from what it cannot", () => {
    const { recoverable, lost } = outlookFor([bundle(), granted]);

    expect(recoverable).toHaveLength(1);
    expect(recoverable[0].generation).toBe(0);
    expect(lost).toHaveLength(1);
    expect(lost[0].generation).toBe(1);
  });

  it("counts a half-written envelope as lost, not as recoverable", () => {
    // A salt without its blob opens nothing. Treating it as recoverable would send the user into a
    // form that fails at the last step, after they had been told it would work.
    const { recoverable, lost } = outlookFor([
      bundle({ recovery_salt: null }),
      bundle({ recovery_wrapped_private_key: null }),
    ]);

    expect(recoverable).toEqual([]);
    expect(lost).toHaveLength(2);
  });

  it("says an account is unrecoverable when nothing carries a recovery copy", () => {
    // The screen must refuse rather than offer a form: every generation here arrived by grant.
    expect(isRecoverable([granted])).toBe(false);
    expect(isRecoverable([])).toBe(false);
    expect(isRecoverable([bundle(), granted])).toBe(true);
  });
});
