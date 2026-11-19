// Instance administration: the client side of /v1/admin.
//
// Metadata only, as the server sends it: an account's address, dates, second factor and
// suspension. Nothing here can read a calendar, and nothing tries.

import { authedFetch } from "@/lib/auth";

export type AdminAccount = {
  id: string;
  email: string;
  name: string;
  created_at: string;
  email_verified: boolean;
  last_login_at: string | null;
  two_factor_enabled: boolean;
  suspended_at: string | null;
  is_admin: boolean;
};

export type RegistrationState = {
  open: boolean;
  /** Pinned by GHOSTCAL_REGISTRATION: show the state, offer no button. */
  fixed: boolean;
};

export function listAccounts(): Promise<AdminAccount[]> {
  return authedFetch<AdminAccount[]>("/v1/admin/accounts");
}

export function getRegistration(): Promise<RegistrationState> {
  return authedFetch<RegistrationState>("/v1/admin/registration");
}

export function setRegistration(open: boolean): Promise<RegistrationState> {
  return authedFetch<RegistrationState>("/v1/admin/registration", {
    method: "PUT",
    body: JSON.stringify({ open }),
  });
}

export function suspendAccount(id: string): Promise<void> {
  return authedFetch<void>(`/v1/admin/accounts/${encodeURIComponent(id)}/suspend`, {
    method: "POST",
  });
}

export function reactivateAccount(id: string): Promise<void> {
  return authedFetch<void>(`/v1/admin/accounts/${encodeURIComponent(id)}/reactivate`, {
    method: "POST",
  });
}

export function deleteAccount(id: string, emailConfirmation: string): Promise<void> {
  return authedFetch<void>(`/v1/admin/accounts/${encodeURIComponent(id)}`, {
    method: "DELETE",
    body: JSON.stringify({ email_confirmation: emailConfirmation }),
  });
}

/** What the view may offer for an account. An administrator is out of reach: the server
 * refuses with 409, and the way to remove one is GHOSTCAL_ADMIN_EMAILS. */
export function actionsFor(account: AdminAccount): ("suspend" | "reactivate" | "delete")[] {
  if (account.is_admin) return [];
  return [account.suspended_at ? "reactivate" : "suspend", "delete"];
}

/** The typed confirmation matches the address, as the server compares it. */
export function confirmationMatches(account: AdminAccount, typed: string): boolean {
  return typed.trim().toLowerCase() === account.email.toLowerCase();
}

/** Opening sign-up asks for confirmation, closing does not: closing loses nothing, opening lets
 * anyone with the address create an account. */
export function needsConfirmation(open: boolean): boolean {
  return open;
}
