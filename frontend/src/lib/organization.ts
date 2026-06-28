// Organization profile (name + public handle) API client.

import { authedFetch } from "@/lib/auth";

export type Organization = { id: string; name: string; slug: string };

export type OrgMembership = { id: string; name: string; slug: string; role: string };

export function getOrganization(): Promise<Organization> {
  return authedFetch<Organization>("/v1/me/organization");
}

export function getMyOrganizations(): Promise<OrgMembership[]> {
  return authedFetch<OrgMembership[]>("/v1/me/organizations");
}

export function updateOrganization(body: {
  name: string;
  slug: string;
}): Promise<Organization> {
  return authedFetch<Organization>("/v1/me/organization", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}
