// Outbound webhooks API client.

import { authedFetch } from "@/lib/auth";

export type Webhook = {
  id: string;
  url: string;
  event_types: string[];
  active: boolean;
  created_at: string;
};

export type WebhookCreated = {
  id: string;
  url: string;
  event_types: string[];
  secret: string;
};

export function listWebhookEvents(): Promise<string[]> {
  return authedFetch<string[]>("/v1/me/webhooks/events");
}

export function listWebhooks(): Promise<Webhook[]> {
  return authedFetch<Webhook[]>("/v1/me/webhooks");
}

export function createWebhook(url: string, eventTypes: string[]): Promise<WebhookCreated> {
  return authedFetch<WebhookCreated>("/v1/me/webhooks", {
    method: "POST",
    body: JSON.stringify({ url, event_types: eventTypes }),
  });
}

export function deleteWebhook(id: string): Promise<void> {
  return authedFetch<void>(`/v1/me/webhooks/${id}`, { method: "DELETE" });
}
