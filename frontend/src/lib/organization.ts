// Organization profile (name + public handle) API client.

import { authedFetch } from "@/lib/auth";

export type Organization = { id: string; name: string; slug: string };

export function getOrganization(): Promise<Organization> {
  return authedFetch<Organization>("/v1/me/organization");
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
