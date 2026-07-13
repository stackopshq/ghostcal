// The rotation-facing surface of per-user keypairs (ADR-0007).
//
// Creating and unlocking the caller's OWN keypair belongs to the login flow and lives in lib/auth.ts
// (it needs the password, which only login has). What is left here is what a *rotating admin* needs:
// the public keys of everyone in the org, which the new org key gets sealed to.

import { authedFetch } from "@/lib/auth";
import { getUserKeys } from "@/lib/zk";

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
