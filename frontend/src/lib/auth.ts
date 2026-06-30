// Client-side auth: token storage + bearer requests with refresh-on-401.
//
// Tokens live in localStorage. Note (matches the backend decision): the refresh token is held
// client-side because the dev setup is cross-origin http; production should move it to an
// httpOnly cookie behind a same-origin proxy.

import { ApiError, resolveBaseUrl } from "@/lib/api";
import {
  clearUnlockedKeys,
  generateKeyMaterial,
  generateRecoveryPhrase,
  listUnlockedKeys,
  rewrapForPassword,
  storeUnlockedKey,
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
  const zk_keys: ZkKeyMaterial = await generateKeyMaterial(password, recoveryPhrase);
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
  public_key: string;
  wrapped_private_key: string;
  wrap_salt: string;
};

export function getZkKeys(): Promise<ZkKeysOut[]> {
  return authedFetch<ZkKeysOut[]>("/v1/auth/zk-keys");
}

// Unwrap every org private key with the password and stash them (keyed by org) in the per-tab
// session store, so the dashboard can decrypt the active org's invitee details. A member of
// several orgs holds a distinct key per org. Best-effort: a failure here never blocks login.
async function unlockZk(password: string): Promise<void> {
  try {
    for (const k of await getZkKeys()) {
      try {
        const privateKey = await unlockWithPassword(password, k.wrapped_private_key, k.wrap_salt);
        storeUnlockedKey(k.organization_id, { publicKey: k.public_key, privateKey });
      } catch {
        /* skip an org whose key this password can't unwrap (e.g. a granted key) */
      }
    }
  } catch {
    /* leave locked; the dashboard will offer to unlock */
  }
}

export function verifyEmail(token: string): Promise<void> {
  return post("/v1/auth/verify-email", { token });
}

export async function login(email: string, password: string): Promise<void> {
  const tokens = await post<Tokens>("/v1/auth/login", { email, password });
  setTokens(tokens);
  await unlockZk(password);
}

// Re-wrap every unlocked org key under a new password and persist them. Call after a successful
// password change so the new password can unlock each org key next time.
export async function rewrapAllForNewPassword(newPassword: string): Promise<void> {
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
    await post("/v1/auth/logout", { refresh_token: refresh }).catch(() => undefined);
  }
}

async function tryRefresh(): Promise<boolean> {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  try {
    const tokens = await post<Tokens>("/v1/auth/refresh", { refresh_token: refresh });
    setTokens(tokens);
    return true;
  } catch {
    clearTokens();
    return false;
  }
}

/** Fetch an authenticated endpoint, transparently refreshing once on a 401. */
export async function authedFetch<T>(path: string, init?: RequestInit): Promise<T> {
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
