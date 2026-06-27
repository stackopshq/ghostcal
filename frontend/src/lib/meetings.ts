// Meetings (bookings) API client.

import { authedFetch } from "@/lib/auth";

export type Meeting = {
  id: string;
  event_title: string;
  invitee_name: string;
  invitee_email: string;
  invitee_timezone: string;
  start_at: string;
  end_at: string;
  status: string;
  location: string | null;
  meeting_url: string | null;
};

export type MeetingScope = "upcoming" | "past";

export function listMeetings(scope: MeetingScope): Promise<Meeting[]> {
  return authedFetch<Meeting[]>(`/v1/me/meetings?scope=${scope}`);
}
