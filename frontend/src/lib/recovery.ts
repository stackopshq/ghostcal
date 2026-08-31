/**
 * Getting back in with the recovery phrase (ADR-0003).
 *
 * The phrase was generated at sign-up, shown once, and then had nothing to spend itself on: the
 * envelope it opens was stored, `unlockWithRecovery` was written, and no code path called either.
 * A forgotten password meant a permanently locked account with the way back sitting in the database.
 *
 * **What a reset can and cannot reopen.** An org key reaches a member two ways: wrapped under their
 * password — and, since it is generated at the same moment, under their recovery phrase — or sealed
 * to their user keypair, which is how a rotated organisation hands out its new generation. Only the
 * first kind has a recovery envelope. The user keypair has none at all
 * (`generateUserKeypair` stores `recovery_wrapped_private_key: ""` on purpose: ADR-0003 says a lost
 * keypair is re-granted, not recovered).
 *
 * So a reset reopens what the phrase wraps, and nothing else. That is a real limit, and the screen
 * has to say it *before* the user commits — handing back an account that silently opens a fraction
 * of its own calendar is worse than refusing, because the missing part looks like deleted data.
 */

import { rewrapForPassword, unlockWithRecovery } from "@/lib/zk";

/** One generation of one org key, as `GET /v1/auth/reset-password/{token}/zk-keys` returns it. */
export type ResetBundle = {
  organization_id: string;
  public_key: string;
  generation: number;
  sealed_org_key: string | null;
  wrapped_private_key: string | null;
  wrap_salt: string | null;
  recovery_wrapped_private_key: string | null;
  recovery_salt: string | null;
};

export type ResetOutlook = {
  /** Generations the phrase can reopen. */
  recoverable: ResetBundle[];
  /** Generations it cannot — sealed to the user keypair, which has no recovery copy. */
  lost: ResetBundle[];
};

/**
 * What this reset will and will not bring back, decided before anything is changed.
 *
 * A bundle is recoverable when it carries a recovery envelope. One that only carries
 * `sealed_org_key` is opened by the user keypair, and the keypair is opened by the password that
 * has just been forgotten — nothing in a reset can reach it.
 */
export function outlookFor(bundles: readonly ResetBundle[]): ResetOutlook {
  const recoverable: ResetBundle[] = [];
  const lost: ResetBundle[] = [];
  for (const b of bundles) {
    if (b.recovery_wrapped_private_key && b.recovery_salt) recoverable.push(b);
    else lost.push(b);
  }
  return { recoverable, lost };
}

/** Whether this account can be reopened at all. False means the phrase is not enough here. */
export function isRecoverable(bundles: readonly ResetBundle[]): boolean {
  return outlookFor(bundles).recoverable.length > 0;
}

export function requestPasswordReset(email: string): Promise<void> {
  // No auth, and no distinction between a known and an unknown address — the server answers 202
  // either way, and so does this.
  return fetch(`/api/v1/auth/forgot-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  }).then(() => undefined);
}

export async function zkKeysForReset(token: string): Promise<ResetBundle[]> {
  const res = await fetch(
    `/api/v1/auth/reset-password/${encodeURIComponent(token)}/zk-keys`,
  );
  if (!res.ok) throw new Error(String(res.status));
  return (await res.json()) as ResetBundle[];
}

/**
 * Open every recoverable generation with the phrase, re-wrap it under the new password, and send
 * the lot with the password itself.
 *
 * One request, deliberately. The server cannot re-wrap anything — it never sees a private key — so
 * a reset that set the password first and the envelopes second would leave, in the gap, exactly the
 * state this feature exists to undo: a working login in front of a calendar nothing opens.
 *
 * Throws if the phrase opens nothing, before any request is sent. AES-GCM authenticates, so a wrong
 * phrase fails loudly rather than yielding a key that decrypts noise.
 */
export async function resetWithRecoveryPhrase(
  token: string,
  bundles: readonly ResetBundle[],
  recoveryPhrase: string,
  newPassword: string,
): Promise<{ reopened: number; stillSealed: number }> {
  const { recoverable, lost } = outlookFor(bundles);

  const envelopes: {
    organization_id: string;
    wrapped_private_key: string;
    wrap_salt: string;
  }[] = [];
  for (const b of recoverable) {
    const privateKey = await unlockWithRecovery(
      recoveryPhrase,
      b.recovery_wrapped_private_key as string,
      b.recovery_salt as string,
    );
    const wrapped = await rewrapForPassword(privateKey, newPassword);
    envelopes.push({
      organization_id: b.organization_id,
      wrapped_private_key: wrapped.wrapped_private_key,
      wrap_salt: wrapped.salt,
    });
  }

  await fetch(`/api/v1/auth/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      token,
      new_password: newPassword,
      envelopes,
    }),
  }).then((res) => {
    if (!res.ok) throw new Error(String(res.status));
  });

  return { reopened: envelopes.length, stillSealed: lost.length };
}
