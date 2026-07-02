// Public ICS calendar subscription API client.
//
// A subscription is a read-only external feed (holidays, sports fixtures, a colleague's public
// calendar…). Its events surface in the agenda as source="subscription" carrying the subscription
// id in calendar_id, so the calendar page colours and toggles them like any other calendar.

import { authedFetch } from "@/lib/auth";

export type Subscription = {
  id: string;
  name: string;
  url: string;
  color: string;
  status: string;
  last_error: string | null;
  last_synced_at: string | null;
};

export function listSubscriptions(): Promise<Subscription[]> {
  return authedFetch<Subscription[]>("/v1/me/calendar/subscriptions");
}

export function addSubscription(body: {
  name: string;
  url: string;
  color?: string;
}): Promise<{ id: string }> {
  return authedFetch<{ id: string }>("/v1/me/calendar/subscriptions", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function refreshSubscription(id: string): Promise<void> {
  return authedFetch<void>(`/v1/me/calendar/subscriptions/${id}/refresh`, { method: "POST" });
}

export function deleteSubscription(id: string): Promise<void> {
  return authedFetch<void>(`/v1/me/calendar/subscriptions/${id}`, { method: "DELETE" });
}
