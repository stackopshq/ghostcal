// Meetings (bookings) API client.

import { authedFetch } from "@/lib/auth";

export type Meeting = {
  id: string;
  event_title: string;
  // Null for booking-page bookings — the real name is inside the zero-knowledge invitee_private blob.
  invitee_name: string | null;
  invitee_email: string;
  invitee_timezone: string;
  start_at: string;
  end_at: string;
  status: string;
  location: string | null;
  meeting_url: string | null;
  // Sealed blob (name + answers + notes); decrypted in the browser with the org private key.
  invitee_private: string | null;
};

export type MeetingScope = "upcoming" | "past";

export function listMeetings(scope: MeetingScope): Promise<Meeting[]> {
  return authedFetch<Meeting[]>(`/v1/me/meetings?scope=${scope}`);
}

export function cancelMeeting(id: string): Promise<void> {
  return authedFetch<void>(`/v1/me/meetings/${id}/cancel`, { method: "POST" });
}
