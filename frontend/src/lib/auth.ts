// Client-side auth: token storage + bearer requests with refresh-on-401.
//
// Tokens live in localStorage. Note (matches the backend decision): the refresh token is held
// client-side because the dev setup is cross-origin http; production should move it to an
// httpOnly cookie behind a same-origin proxy.

import { ApiError, resolveBaseUrl } from "@/lib/api";
import {
  clearUnlockedKeys,
  generateKeyMaterial,
  generateUserKeypair,
  generateRecoveryPhrase,
  listUnlockedKeys,
  rewrapForPassword,
  getUserKeys,
  openOrgKeyForMe,
  storeUnlockedKey,
  storeUserKeys,
  unlockUserPrivateKey,
  unlockWithPassword,
  type ZkKeyMaterial,
} from "@/lib/zk";

const ACCESS_KEY = "gc_access";
const REFRESH_KEY = "gc_refresh";
const ORG_KEY = "gc_org";

export function getActiveOrg(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ORG_KEY);
}

export function setActiveOrg(orgId: string | null): void {
  if (orgId) localStorage.setItem(ORG_KEY, orgId);
  else localStorage.removeItem(ORG_KEY);
}

export type User = {
  id: string;
  email: string;
  name: string;
  email_verified: boolean;
  // False for an SSO-only account: it has no password, so deletion is confirmed by the email alone.
  has_password: boolean;
};

type Tokens = { access_token: string; refresh_token: string };

function base(): string {
  return resolveBaseUrl();
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_KEY);
}

function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY);
}

function setTokens(tokens: Tokens): void {
  localStorage.setItem(ACCESS_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(ORG_KEY);
}

export function isAuthenticated(): boolean {
  return getAccessToken() !== null;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${base()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new ApiError(res.status, detail || res.statusText);
  }
  // 204 responses have no body.
  return (res.status === 204 ? undefined : await res.json()) as T;
}

// Sign-up generates the org keypair in the browser. The private key is wrapped under the password
// and under a one-time recovery phrase (shown to the user); the server only ever receives the
// public key and the wrapped blobs. Returns the recovery phrase so the page can display it once.
export async function register(
  email: string,
  name: string,
  password: string,
): Promise<{ user_id: string; recovery_phrase: string }> {
  const recoveryPhrase = await generateRecoveryPhrase();
  const zk_keys: ZkKeyMaterial = await generateKeyMaterial(
    password,
    recoveryPhrase,
  );
  const { user_id } = await post<{ user_id: string }>("/v1/auth/register", {
    email,
    name,
    password,
    zk_keys,
  });
  return { user_id, recovery_phrase: recoveryPhrase };
}

export type ZkKeysOut = {
  organization_id: string;
  /** The org's CURRENT public key, whatever generation this row is. */
  public_key: string;
  generation: number;
  /** Generation >= 1: the org key sealed to the user's own public key (ADR-0007). */
  sealed_org_key: string | null;
  /** Generation 0: wrapped under a key derived from the user's password. */
  wrapped_private_key: string | null;
  wrap_salt: string | null;
};

export function getZkKeys(): Promise<ZkKeysOut[]> {
  return authedFetch<ZkKeysOut[]>("/v1/auth/zk-keys");
}

// Unwrap every org private key with the given secret (login password, or an SSO user's encryption
// passphrase — same wrap) and stash them (keyed by org) in the per-tab session store, so the
// dashboard can decrypt the active org's content. Returns how many of the user's org keys unlocked,
// so a caller (the unlock screen) can tell a wrong passphrase from an empty vault.
export async function unlockZkKeys(
  secret: string,
): Promise<{ total: number; unlocked: number }> {
  // The user's own private key has to exist first: from generation 1 on, an org key reaches a member
  // sealed to it, and without it those generations simply cannot be opened.
  await ensureUserKeypair(secret);
  const userKeys = getUserKeys();

  const rows = await getZkKeys();
  const byOrg = new Map<string, ZkKeysOut[]>();
  for (const row of rows) {
    byOrg.set(row.organization_id, [
      ...(byOrg.get(row.organization_id) ?? []),
      row,
    ]);
  }

  let unlocked = 0;
  for (const [organizationId, generations] of byOrg) {
    // Newest generation first — that is the one everything new is sealed under, and the one the
    // fallback chain starts from.
    const ordered = [...generations].sort(
      (a, b) => b.generation - a.generation,
    );
    const privateKeys: string[] = [];

    for (const row of ordered) {
      try {
        if (row.sealed_org_key) {
          if (!userKeys) continue; // no user key in this tab: this generation stays shut
          privateKeys.push(
            await openOrgKeyForMe(row.sealed_org_key, userKeys.privateKey),
          );
        } else if (row.wrapped_private_key && row.wrap_salt) {
          privateKeys.push(
            await unlockWithPassword(
              secret,
              row.wrapped_private_key,
              row.wrap_salt,
            ),
          );
        }
      } catch {
        /* a generation this secret or key cannot open (e.g. a granted key); skip it */
      }
    }

    if (privateKeys.length > 0) {
      storeUnlockedKey(organizationId, {
        publicKey: ordered[0].public_key,
        privateKey: privateKeys[0],
        previousPrivateKeys: privateKeys.slice(1),
      });
      unlocked += 1;
    }
  }
  return { total: byOrg.size, unlocked };
}

// --- The user's own keypair (ADR-0007) ---------------------------------------------------------
//
// Distinct from the ORG keypair: an org key can be sealed TO this one, which is what lets an admin
// rotate an org keypair without any member lifting a finger. It can only be created while the
// password is in the browser, so login is the moment — hence its home here rather than in
// lib/keypair.ts, which keeps the rotation-facing half.

export type UserKeypair = {
  public_key: string;
  wrapped_private_key: string;
  wrap_salt: string;
};

export function getKeypair(): Promise<UserKeypair | null> {
  return authedFetch<UserKeypair | null>("/v1/me/keypair");
}

export function putKeypair(keypair: UserKeypair): Promise<void> {
  return authedFetch<void>("/v1/me/keypair", {
    method: "PUT",
    body: JSON.stringify(keypair),
  });
}

// Make sure the account has a keypair, and stash it unlocked for this tab. Best-effort by design:
// failing here must never keep someone out of their account. The worst case is that an org cannot
// rotate past them yet, and their next login fixes it.
export async function ensureUserKeypair(secret: string): Promise<void> {
  try {
    let keypair = await getKeypair();

    if (keypair === null) {
      const generated = await generateUserKeypair(secret);
      keypair = {
        public_key: generated.public_key,
        wrapped_private_key: generated.wrapped_private_key,
        wrap_salt: generated.wrap_salt,
      };
      try {
        await putKeypair(keypair);
      } catch {
        // 409: another tab published one first. Theirs won — take it, or we would sit on a private
        // key that nothing will ever be sealed to.
        keypair = await getKeypair();
        if (keypair === null) return;
      }
    }

    storeUserKeys({
      publicKey: keypair.public_key,
      privateKey: await unlockUserPrivateKey(
        secret,
        keypair.wrapped_private_key,
        keypair.wrap_salt,
      ),
    });
  } catch {
    /* a secret that cannot unwrap the stored keypair; leave it locked, nothing else breaks */
  }
}

// Best-effort unlock used by password login — a failure here never blocks login.
async function unlockZk(password: string): Promise<void> {
  try {
    await unlockZkKeys(password);
  } catch {
    /* leave locked; the dashboard will offer to unlock */
  }
}

/** Whether the user already has zero-knowledge keys (i.e. has set an encryption passphrase). */
export async function hasZkKeys(): Promise<boolean> {
  return (await getZkKeys()).length > 0;
}

export function verifyEmail(token: string): Promise<void> {
  return post("/v1/auth/verify-email", { token });
}

export async function login(email: string, password: string): Promise<void> {
  const tokens = await post<Tokens>("/v1/auth/login", { email, password });
  setTokens(tokens);
  await unlockZk(password);
}

// --- SSO / OIDC ---------------------------------------------------------------------------------

export type AuthConfig = { oidc_enabled: boolean };

export async function getAuthConfig(): Promise<AuthConfig> {
  const res = await fetch(`${base()}/v1/auth/config`, { cache: "no-store" });
  if (!res.ok) return { oidc_enabled: false };
  return (await res.json()) as AuthConfig;
}

/** Send the browser to the backend OIDC start route, which 302s to the identity provider. */
export function beginOidcLogin(): void {
  window.location.assign(`${base()}/v1/auth/oidc/login`);
}

// The OIDC callback lands on /auth/callback with the session tokens in the URL *fragment* (never
// sent to a server). Read them into storage and strip the fragment from the address bar/history.
export function completeOidcSession(): boolean {
  if (typeof window === "undefined") return false;
  const hash = window.location.hash.replace(/^#/, "");
  if (!hash) return false;
  const params = new URLSearchParams(hash);
  const access = params.get("access_token");
  const refresh = params.get("refresh_token");
  if (!access || !refresh) return false;
  setTokens({ access_token: access, refresh_token: refresh });
  history.replaceState(null, "", window.location.pathname);
  return true;
}

// First-time SSO users have no zero-knowledge keys: they choose an encryption passphrase (separate
// from SSO — the server never sees it), which wraps a fresh org keypair. Returns the one-time
// recovery phrase to show once. The keys are unlocked into this tab immediately.
export async function setupEncryptionPassphrase(
  passphrase: string,
): Promise<string> {
  const recoveryPhrase = await generateRecoveryPhrase();
  const zk_keys: ZkKeyMaterial = await generateKeyMaterial(
    passphrase,
    recoveryPhrase,
  );
  await authedFetch<void>("/v1/auth/zk-keys", {
    method: "POST",
    body: JSON.stringify(zk_keys),
  });
  await unlockZkKeys(passphrase);
  return recoveryPhrase;
}

// Re-wrap every unlocked org key under a new password and persist them. Call after a successful
// password change so the new password can unlock each org key next time.
export async function rewrapAllForNewPassword(
  newPassword: string,
): Promise<void> {
  for (const { organizationId, keys } of listUnlockedKeys()) {
    const wrapped = await rewrapForPassword(keys.privateKey, newPassword);
    await authedFetch<void>("/v1/auth/zk-rewrap", {
      method: "POST",
      body: JSON.stringify({
        organization_id: organizationId,
        wrapped_private_key: wrapped.wrapped_private_key,
        wrap_salt: wrapped.salt,
      }),
    });
  }
}

export async function logout(): Promise<void> {
  const refresh = getRefreshToken();
  clearTokens();
  clearUnlockedKeys();
  if (refresh) {
    await post("/v1/auth/logout", { refresh_token: refresh }).catch(
      () => undefined,
    );
  }
}

async function tryRefresh(): Promise<boolean> {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  try {
    const tokens = await post<Tokens>("/v1/auth/refresh", {
      refresh_token: refresh,
    });
    setTokens(tokens);
    return true;
  } catch {
    clearTokens();
    return false;
  }
}

/** Fetch an authenticated endpoint, transparently refreshing once on a 401. */
export async function authedFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const org = getActiveOrg();
  const run = async (): Promise<Response> =>
    fetch(`${base()}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...init?.headers,
        Authorization: `Bearer ${getAccessToken() ?? ""}`,
        ...(org ? { "X-Organization-Id": org } : {}),
      },
      cache: "no-store",
    });

  let res = await run();
  if (res.status === 401 && (await tryRefresh())) {
    res = await run();
  }
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new ApiError(res.status, detail || res.statusText);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export function getMe(): Promise<User> {
  return authedFetch<User>("/v1/auth/me");
}
