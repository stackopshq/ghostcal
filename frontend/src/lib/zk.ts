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

async function wrap(
  privateKeyBytes: Uint8Array<ArrayBuffer>,
  passphrase: string,
): Promise<WrappedKey> {
  const salt = crypto.getRandomValues(new Uint8Array(ARGON2_SALT_BYTES));
  const key = await deriveKey(passphrase, salt);
  return {
    wrapped_private_key: await encryptSymmetric(key, privateKeyBytes),
    salt: toB64(salt),
  };
}

async function unwrap(
  wrappedBlob: string,
  saltB64: string,
  passphrase: string,
): Promise<Uint8Array> {
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
export async function rewrapForPassword(
  privateKeyB64: string,
  newPassword: string,
): Promise<WrappedKey> {
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
    wrapped_org_key: await encryptSymmetric(
      grantKey,
      fromB64(orgPrivateKeyB64),
    ),
  };
}

/** Recover the org private key from a grant blob using the fragment grant key. */
export async function unwrapKeyFromGrant(
  grantKeyB64Url: string,
  wrappedOrgKey: string,
): Promise<string> {
  return toB64(
    await decryptSymmetric(fromB64Url(grantKeyB64Url), wrappedOrgKey),
  );
}

// --- Unlocked-key session store ----------------------------------------------------------------
// The unwrapped org keypairs live in sessionStorage, keyed by organization id: per-tab, cleared on
// tab close, never written to disk. A member of several orgs holds a distinct key per org, so the
// dashboard reads the keypair for the *active* org.

const KEYS = "gc_zk_keys";

export type UnlockedKeys = {
  /** The org's CURRENT public key. Everything new is sealed to this one. */
  publicKey: string;
  /** The CURRENT generation's private key. */
  privateKey: string;
  /**
   * Private keys of retired generations, newest first (ADR-0007). A record sealed before a rotation
   * and not yet re-sealed still needs the key it was sealed under, so we keep them all and open by
   * trying in turn — a sealed blob carries no key id.
   */
  previousPrivateKeys?: string[];
};

/**
 * Open a sealed blob with whichever generation of the org key actually sealed it.
 *
 * Tries the current key first (the common case) and falls back through the retired ones. AES-GCM
 * authenticates, so a wrong key throws rather than returning plausible garbage: the cost of guessing
 * is a failed decryption, never a wrong answer.
 */
export async function openWithOrgKeys<T>(
  keys: UnlockedKeys,
  blob: string,
  open: (blob: string, privateKey: string) => Promise<T>,
): Promise<T> {
  const candidates = [keys.privateKey, ...(keys.previousPrivateKeys ?? [])];
  let lastError: unknown = new Error("no org key available");
  for (const privateKey of candidates) {
    try {
      return await open(blob, privateKey);
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError;
}

function readMap(): Record<string, UnlockedKeys> {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(sessionStorage.getItem(KEYS) ?? "{}") as Record<
      string,
      UnlockedKeys
    >;
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
export function listUnlockedKeys(): Array<{
  organizationId: string;
  keys: UnlockedKeys;
}> {
  return Object.entries(readMap()).map(([organizationId, keys]) => ({
    organizationId,
    keys,
  }));
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
  sessionStorage.removeItem(USER_KEY);
}

// --- The user's own keypair (ADR-0007) ---------------------------------------------------------
//
// Distinct from the ORG keypair above. An org key can be sealed *to* this public key, which is what
// lets an admin rotate the org keypair without every member having to do anything: they log in, and
// their browser opens the new org key with the private key below.

const USER_KEY = "gc_zk_user";

/** Generate the user's own keypair, wrapping the private key under their password. */
export async function generateUserKeypair(
  secret: string,
): Promise<ZkKeyMaterial> {
  const kp = await generateKeypair();
  const wrapped = await wrap(fromB64(kp.privateKey), secret);
  return {
    public_key: kp.publicKey,
    wrapped_private_key: wrapped.wrapped_private_key,
    wrap_salt: wrapped.salt,
    // A user keypair has no recovery copy: a forgotten password loses it, and the org keys sealed
    // to it are simply re-granted — exactly as ADR-0003 already provides for a granted key.
    recovery_wrapped_private_key: "",
    recovery_salt: "",
  };
}

/** Unwrap the user's own private key with their password. Throws on a wrong secret (AES-GCM auth). */
export async function unlockUserPrivateKey(
  secret: string,
  wrappedB64: string,
  saltB64: string,
): Promise<string> {
  return toB64(await unwrap(wrappedB64, saltB64, secret));
}

export function storeUserKeys(keys: UnlockedKeys): void {
  sessionStorage.setItem(USER_KEY, JSON.stringify(keys));
}

export function getUserKeys(): UnlockedKeys | null {
  if (typeof window === "undefined") return null;
  try {
    return JSON.parse(
      sessionStorage.getItem(USER_KEY) ?? "null",
    ) as UnlockedKeys | null;
  } catch {
    return null;
  }
}

/**
 * Re-seal a blob from whichever retired key opened it to the org's current key (ADR-0007).
 *
 * Note what this does NOT do: parse the plaintext. It moves bytes from one envelope to another, so
 * it works for an invitee blob, an event's content and a task's content alike, and it keeps working
 * if what is inside them ever changes. The re-seal pass has no business knowing what it is carrying.
 */
export async function reseal(
  blob: string,
  keys: UnlockedKeys,
): Promise<string> {
  const plaintext = await openWithOrgKeys(keys, blob, (b, privateKey) =>
    openSealed(privateKey, b),
  );
  return sealToPublicKey(keys.publicKey, plaintext);
}

/** A fresh org keypair for a rotation. Unlike sign-up, nothing is wrapped under a password: the new
 * private key reaches each member sealed to *their* public key instead (ADR-0007). */
export async function generateOrgKeypair(): Promise<{
  publicKey: string;
  privateKey: string;
}> {
  return generateKeypair();
}

/** Seal an org private key TO a member's public key — the move a rotation is built on. */
export async function sealOrgKeyToMember(
  orgPrivateKeyB64: string,
  memberPublicKeyB64: string,
): Promise<string> {
  return sealToPublicKey(memberPublicKeyB64, fromB64(orgPrivateKeyB64));
}

/** Open an org private key that was sealed to my public key. */
export async function openOrgKeyForMe(
  sealed: string,
  myPrivateKeyB64: string,
): Promise<string> {
  return toB64(await openSealed(myPrivateKeyB64, sealed));
}

// --- Invitee blob (booking page ⇄ dashboard) ---------------------------------------------------

/** Seal the invitee's private details to the org public key (booking page). */
export async function sealInviteePrivate(
  data: InviteePrivate,
  orgPublicKeyB64: string,
): Promise<string> {
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

// --- Calendar event content (zero-knowledge calendar, ADR-0004) ---------------------------------

export type EventContent = {
  title: string;
  description: string;
  location: string;
};

/** Seal an event's content (title/description/location) to the org public key. */
export async function sealContent(
  data: EventContent,
  orgPublicKeyB64: string,
): Promise<string> {
  return sealToPublicKey(orgPublicKeyB64, enc.encode(JSON.stringify(data)));
}

/** Open a sealed event content blob with the org private key. */
export async function openContent(
  blob: string,
  orgPrivateKeyB64: string,
): Promise<EventContent> {
  return JSON.parse(
    dec.decode(await openSealed(orgPrivateKeyB64, blob)),
  ) as EventContent;
}

export type TaskContent = { title: string; notes: string };

/** Seal a task's content (title/notes) to the org public key. */
export async function sealTaskContent(
  data: TaskContent,
  orgPublicKeyB64: string,
): Promise<string> {
  return sealToPublicKey(orgPublicKeyB64, enc.encode(JSON.stringify(data)));
}

/** Open a sealed task content blob with the org private key. */
export async function openTaskContent(
  blob: string,
  orgPrivateKeyB64: string,
): Promise<TaskContent> {
  return JSON.parse(
    dec.decode(await openSealed(orgPrivateKeyB64, blob)),
  ) as TaskContent;
}
