// Organization members + invitations API client.

import { authedFetch } from "@/lib/auth";

export type Member = {
  user_id: string;
  name: string;
  email: string;
  role: string;
  joined_at: string;
};

export type Invitation = {
  id: string;
  email: string;
  role: string;
  created_at: string;
  expires_at: string;
  // Returned only on creation, so the inviter can build the secure accept link (#k fragment).
  token?: string | null;
};

export function listMembers(): Promise<Member[]> {
  return authedFetch<Member[]>("/v1/me/organization/members");
}

export function changeRole(userId: string, role: string): Promise<Member[]> {
  return authedFetch<Member[]>(`/v1/me/organization/members/${userId}`, {
    method: "PATCH",
    body: JSON.stringify({ role }),
  });
}

export function removeMember(userId: string): Promise<void> {
  return authedFetch<void>(`/v1/me/organization/members/${userId}`, { method: "DELETE" });
}

export function listInvitations(): Promise<Invitation[]> {
  return authedFetch<Invitation[]>("/v1/me/organization/invitations");
}

export function inviteMember(
  email: string,
  role: string,
  wrappedOrgKey: string | null,
): Promise<Invitation> {
  return authedFetch<Invitation>("/v1/me/organization/invitations", {
    method: "POST",
    body: JSON.stringify({ email, role, wrapped_org_key: wrappedOrgKey }),
  });
}

/** Persist a member's org key (re-wrapped under their password) after recovering it from a grant. */
export function storeMemberKey(
  organizationId: string,
  wrappedPrivateKey: string,
  wrapSalt: string,
): Promise<void> {
  return authedFetch<void>("/v1/invitations/member-key", {
    method: "POST",
    body: JSON.stringify({
      organization_id: organizationId,
      wrapped_private_key: wrappedPrivateKey,
      wrap_salt: wrapSalt,
    }),
  });
}

export function revokeInvitation(id: string): Promise<void> {
  return authedFetch<void>(`/v1/me/organization/invitations/${id}`, { method: "DELETE" });
}

export function acceptInvitation(token: string): Promise<{ organization_id: string }> {
  return authedFetch<{ organization_id: string }>(`/v1/invitations/${token}/accept`, {
    method: "POST",
  });
}
