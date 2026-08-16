// "Email guests" bridge to GhostMail (the sibling mail app). Fully decoupled, the mirror of
// GhostMail's "Add to calendar": we hand GhostMail a compose deep-link (recipients + subject + body)
// and it opens its composer prefilled. GhostCal never calls GhostMail's backend; the message is
// written and encrypted entirely in the GhostMail session.
//
// ── Where GhostMail lives, and why it is not a NEXT_PUBLIC_ variable
//
// It used to be `process.env.NEXT_PUBLIC_GHOSTMAIL_URL ?? "http://localhost:3002"`. Next inlines
// NEXT_PUBLIC_* at BUILD time, so the published image carried that localhost address inside its
// JavaScript bundle and setting the variable on the host changed nothing. Measured 2026-08-16 on
// the Apollo deployment: the button opened a dead tab on the user's own machine, silently.
//
// The address is a per-deployment fact, so the deployment answers it — the API serves it at
// `/v1/auth/config`, where the frontend already learns whether SSO exists. One image, many
// deployments.

import { getAuthConfig } from "@/lib/auth";

let cache: string | null | undefined;

/** The configured GhostMail base URL, or null when this deployment has none.
 *
 * Memoised for the tab's lifetime: it is deployment configuration, it does not change under the
 * user's feet, and every guest list would otherwise ask again.
 */
export async function ghostMailUrl(): Promise<string | null> {
  if (cache !== undefined) return cache;
  try {
    cache = (await getAuthConfig()).ghostmail_url ?? null;
  } catch {
    // An unreachable API must not break the page hosting the button. Deliberately not cached:
    // a transient failure should be retried, unlike a deployment that genuinely has no GhostMail.
    return null;
  }
  return cache;
}

/** Forget the memoised value. Tests only — production has no reason to. */
export function resetGhostMailUrlCache(): void {
  cache = undefined;
}

/**
 * Open GhostMail's composer prefilled (the user reviews and sends).
 *
 * The body is optional because "email these guests about this event" needs no body — the subject
 * carries it. "Here is when I am free" is the opposite: the link *is* the message.
 *
 * Returns false when no GhostMail is configured, so a caller that shows the button anyway learns
 * nothing happened instead of opening a tab into the void.
 */
export async function openInGhostMail({
  to,
  subject,
  body = "",
}: {
  to: string[];
  subject: string;
  body?: string;
}): Promise<boolean> {
  const url = await ghostMailUrl();
  if (!url) return false;
  const qs = new URLSearchParams({ compose: "1", to: to.join(","), subject });
  if (body) qs.set("body", body);
  window.open(`${url.replace(/\/$/, "")}/dashboard?${qs}`, "_blank", "noopener");
  return true;
}
