// Analytics API client.

import { authedFetch } from "@/lib/auth";

export type Analytics = {
  total_bookings: number;
  upcoming_bookings: number;
  bookings_last_30_days: number;
  cancellations_last_30_days: number;
  by_event_type: { title: string; count: number }[];
  daily: { day: string; count: number }[];
};

export function getAnalytics(): Promise<Analytics> {
  return authedFetch<Analytics>("/v1/me/analytics");
}
