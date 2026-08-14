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
  /** Les événements de ce flux rendent-ils les créneaux non réservables ? */
  blocks_availability: boolean;
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
  blocks_availability?: boolean;
}): Promise<{ id: string }> {
  return authedFetch<{ id: string }>("/v1/me/calendar/subscriptions", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Bascule un abonnement DÉJÀ créé — sinon il faudrait le supprimer et le
 *  recréer, donc perdre sa couleur et sa place. */
export function setSubscriptionBlocking(id: string, blocking: boolean): Promise<void> {
  return authedFetch<void>(`/v1/me/calendar/subscriptions/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ blocks_availability: blocking }),
  });
}

export function refreshSubscription(id: string): Promise<void> {
  return authedFetch<void>(`/v1/me/calendar/subscriptions/${id}/refresh`, { method: "POST" });
}

export function deleteSubscription(id: string): Promise<void> {
  return authedFetch<void>(`/v1/me/calendar/subscriptions/${id}`, { method: "DELETE" });
}
