// User profile API client.

import { authedFetch } from "@/lib/auth";

export type Profile = {
  id: string;
  email: string;
  name: string;
  timezone: string;
  email_verified: boolean;
  avatar_url: string | null;
};

export function getProfile(): Promise<Profile> {
  return authedFetch<Profile>("/v1/me/profile");
}

export function updateProfile(body: {
  name: string;
  timezone: string;
  avatar_url: string | null;
}): Promise<Profile> {
  return authedFetch<Profile>("/v1/me/profile", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function changePassword(body: {
  current_password: string;
  new_password: string;
}): Promise<void> {
  return authedFetch<void>("/v1/me/profile/password", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
