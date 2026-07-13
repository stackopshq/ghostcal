// The rotation-facing surface of per-user keypairs (ADR-0007).
//
// Creating and unlocking the caller's OWN keypair belongs to the login flow and lives in lib/auth.ts
// (it needs the password, which only login has). What is left here is what a *rotating admin* needs:
// the public keys of everyone in the org, which the new org key gets sealed to.

import { authedFetch } from "@/lib/auth";
import {
  generateOrgKeypair,
  getUnlockedKeys,
  getUserKeys,
  sealOrgKeyToMember,
  storeUnlockedKey,
} from "@/lib/zk";

export type MemberPublicKey = {
  user_id: string;
  name: string;
  email: string;
  /** Null for a member who has not logged in since keypairs shipped — a rotation cannot pass them. */
  public_key: string | null;
};

export function getMemberPublicKeys(): Promise<MemberPublicKey[]> {
  return authedFetch<MemberPublicKey[]>("/v1/me/organization/member-keys");
}

/** Members a rotation would lock out: they have no public key to seal the new org key to. */
export function membersWithoutKeys(
  members: MemberPublicKey[],
): MemberPublicKey[] {
  return members.filter((m) => m.public_key === null);
}

/** Whether this tab holds the user's own private key — required to receive a rotated org key. */
export function hasUnlockedUserKey(): boolean {
  return getUserKeys() !== null;
}

export type RotateResult = { generation: number };

/**
 * Rotate the organization's keypair (ADR-0007) — the act that makes removing a member revoke
 * something.
 *
 * All of it happens here, in the browser. A new pair is minted, and the new private key is sealed to
 * each member's public key, one blob per member. The server receives the new PUBLIC key and those
 * blobs, and can open none of them.
 *
 * It does not re-seal the existing records: advancing the public key already protects everything
 * created from now on, which is the urgent half. The backlog is a separate, resumable pass — a
 * rotation interrupted halfway leaves the org sound, not broken (ADR-0007 §2).
 */
export async function rotateOrgKey(organizationId: string): Promise<number> {
  const members = await getMemberPublicKeys();

  const stragglers = membersWithoutKeys(members);
  if (stragglers.length > 0) {
    // Sealing to nothing would lock them out of their own organization's data, and only they would
    // ever find out. Refuse here too, not just server-side, so the admin is told before they commit.
    throw new MembersNotReady(stragglers);
  }

  const fresh = await generateOrgKeypair();
  const member_keys = await Promise.all(
    members.map(async (m) => ({
      user_id: m.user_id,
      sealed_org_key: await sealOrgKeyToMember(
        fresh.privateKey,
        m.public_key as string,
      ),
    })),
  );

  const { generation } = await authedFetch<RotateResult>(
    "/v1/me/organization/rotate-key",
    {
      method: "POST",
      body: JSON.stringify({ public_key: fresh.publicKey, member_keys }),
    },
  );

  // Carry the new key into this tab, keeping the retired ones: records not yet re-sealed still open
  // with the key they were sealed under.
  const held = getUnlockedKeys(organizationId);
  storeUnlockedKey(organizationId, {
    publicKey: fresh.publicKey,
    privateKey: fresh.privateKey,
    previousPrivateKeys: held
      ? [held.privateKey, ...(held.previousPrivateKeys ?? [])]
      : [],
  });

  return generation;
}

/** The members a rotation cannot provide for. Naming them is the point. */
export class MembersNotReady extends Error {
  constructor(readonly members: MemberPublicKey[]) {
    super("some members have no encryption key yet");
  }
}
