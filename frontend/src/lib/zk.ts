// Zero-knowledge crypto for GhostCal, on the vendored WebCrypto core (lib/e2e).
//
// Each organization has an X25519 keypair. Invitees seal their private details to the org PUBLIC
// key with an anonymous ECIES seal (X25519 ECDH → HKDF → AES-256-GCM) — they need no key of their
// own. Only the holder of the org PRIVATE key (a host, in their browser) can open them; the server
// only ever stores ciphertext. The private key (PKCS#8) is wrapped with AES-256-GCM under a key
// derived from the host's password via Argon2id, and a second time under a one-time recovery
// phrase. Team members receive the key through an invitation-link fragment (see ADR-0003).

import {
  ARGON2_SALT_BYTES,
  decryptSymmetric,
  deriveKey,
  encryptSymmetric,
  fromB64,
  fromB64Url,
  generateKeypair,
  openSealed,
  randomKey,
  sealToPublicKey,
  toB64,
  toB64Url,
} from "@/lib/e2e";

export type WrappedKey = { wrapped_private_key: string; salt: string };

export type ZkKeyMaterial = {
  public_key: string;
  wrapped_private_key: string;
  wrap_salt: string;
  recovery_wrapped_private_key: string;
  recovery_salt: string;
};

/** The cleartext the invitee seals — everything the server must never read. */
export type InviteePrivate = {
  name: string;
  answers: Record<string, string>;
  notes: string;
};

const enc = new TextEncoder();
const dec = new TextDecoder();

async function wrap(privateKeyBytes: Uint8Array<ArrayBuffer>, passphrase: string): Promise<WrappedKey> {
  const salt = crypto.getRandomValues(new Uint8Array(ARGON2_SALT_BYTES));
  const key = await deriveKey(passphrase, salt);
  return { wrapped_private_key: await encryptSymmetric(key, privateKeyBytes), salt: toB64(salt) };
}

async function unwrap(wrappedBlob: string, saltB64: string, passphrase: string): Promise<Uint8Array> {
  const key = await deriveKey(passphrase, fromB64(saltB64));
  return decryptSymmetric(key, wrappedBlob); // AES-GCM auth fails (throws) on a wrong passphrase
}

/** A high-entropy recovery phrase shown once at sign-up (24 random bytes, grouped for legibility). */
export async function generateRecoveryPhrase(): Promise<string> {
  const raw = toB64Url(crypto.getRandomValues(new Uint8Array(24)));
  return (raw.match(/.{1,4}/g) ?? [raw]).join("-");
}

/** Generate a fresh org keypair and wrap the private key under the password and the recovery phrase. */
export async function generateKeyMaterial(
  password: string,
  recoveryPhrase: string,
): Promise<ZkKeyMaterial> {
  const kp = await generateKeypair();
  const privBytes = fromB64(kp.privateKey);
  const byPassword = await wrap(privBytes, password);
  const byRecovery = await wrap(privBytes, recoveryPhrase);
  return {
    public_key: kp.publicKey,
    wrapped_private_key: byPassword.wrapped_private_key,
    wrap_salt: byPassword.salt,
    recovery_wrapped_private_key: byRecovery.wrapped_private_key,
    recovery_salt: byRecovery.salt,
  };
}

/** Unwrap the private key with the password (login) — returns it base64, or throws on a bad password. */
export async function unlockWithPassword(
  password: string,
  wrappedB64: string,
  saltB64: string,
): Promise<string> {
  return toB64(await unwrap(wrappedB64, saltB64, password));
}

/** Unwrap with the recovery phrase (password reset) — returns the private key base64. */
export async function unlockWithRecovery(
  recoveryPhrase: string,
  wrappedB64: string,
  saltB64: string,
): Promise<string> {
  return toB64(await unwrap(wrappedB64, saltB64, recoveryPhrase.trim()));
}

/** Re-wrap a known private key under a new password (after a password change/reset). */
export async function rewrapForPassword(privateKeyB64: string, newPassword: string): Promise<WrappedKey> {
  return wrap(fromB64(privateKeyB64), newPassword);
}

// --- Team key sharing (invitation-link fragment) -----------------------------------------------

/** Seal the org private key under a fresh random grant key (carried in the invite link fragment). */
export async function wrapKeyForGrant(
  orgPrivateKeyB64: string,
): Promise<{ grant_key: string; wrapped_org_key: string }> {
  const grantKey = randomKey();
  return {
    grant_key: toB64Url(grantKey),
    wrapped_org_key: await encryptSymmetric(grantKey, fromB64(orgPrivateKeyB64)),
  };
}

/** Recover the org private key from a grant blob using the fragment grant key. */
export async function unwrapKeyFromGrant(grantKeyB64Url: string, wrappedOrgKey: string): Promise<string> {
  return toB64(await decryptSymmetric(fromB64Url(grantKeyB64Url), wrappedOrgKey));
}

// --- Unlocked-key session store ----------------------------------------------------------------
// The unwrapped org keypairs live in sessionStorage, keyed by organization id: per-tab, cleared on
// tab close, never written to disk. A member of several orgs holds a distinct key per org, so the
// dashboard reads the keypair for the *active* org.

const KEYS = "gc_zk_keys";

export type UnlockedKeys = { publicKey: string; privateKey: string };

function readMap(): Record<string, UnlockedKeys> {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(sessionStorage.getItem(KEYS) ?? "{}") as Record<string, UnlockedKeys>;
  } catch {
    return {};
  }
}

export function storeUnlockedKey(orgId: string, keys: UnlockedKeys): void {
  const map = readMap();
  map[orgId] = keys;
  sessionStorage.setItem(KEYS, JSON.stringify(map));
}

/** Every unlocked org keypair, with its org id (e.g. to re-wrap all keys on a password change). */
export function listUnlockedKeys(): Array<{ organizationId: string; keys: UnlockedKeys }> {
  return Object.entries(readMap()).map(([organizationId, keys]) => ({ organizationId, keys }));
}

/** The keypair for an org (defaults to any unlocked org when no id is given). */
export function getUnlockedKeys(orgId?: string | null): UnlockedKeys | null {
  const map = readMap();
  if (orgId && map[orgId]) return map[orgId];
  if (orgId) return null;
  const first = Object.values(map)[0];
  return first ?? null;
}

export function clearUnlockedKeys(): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(KEYS);
}

// --- Invitee blob (booking page ⇄ dashboard) ---------------------------------------------------

/** Seal the invitee's private details to the org public key (booking page). */
export async function sealInviteePrivate(data: InviteePrivate, orgPublicKeyB64: string): Promise<string> {
  return sealToPublicKey(orgPublicKeyB64, enc.encode(JSON.stringify(data)));
}

/** Open a sealed invitee blob with the org private key (host dashboard). */
export async function openInviteePrivate(
  blob: string,
  _orgPublicKeyB64: string,
  orgPrivateKeyB64: string,
): Promise<InviteePrivate> {
  const opened = await openSealed(orgPrivateKeyB64, blob);
  return JSON.parse(dec.decode(opened)) as InviteePrivate;
}
