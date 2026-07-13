// "Email guests" bridge to GhostMail (the sibling mail app). Fully decoupled, the mirror of
// GhostMail's "Add to calendar": we hand GhostMail a compose deep-link (recipients + subject + body)
// and it opens its composer prefilled. GhostCal never calls GhostMail's backend; the message is
// written and encrypted entirely in the GhostMail session.

// Where GhostMail lives. Configurable per deployment; sensible dev default.
const GHOSTMAIL_URL = process.env.NEXT_PUBLIC_GHOSTMAIL_URL ?? "http://localhost:3002";

/**
 * Open GhostMail's composer prefilled (the user reviews and sends).
 *
 * The body is optional because "email these guests about this event" needs no body — the subject
 * carries it. "Here is when I am free" is the opposite: the link *is* the message.
 */
export function openInGhostMail({
  to,
  subject,
  body = "",
}: {
  to: string[];
  subject: string;
  body?: string;
}): void {
  const qs = new URLSearchParams({ compose: "1", to: to.join(","), subject });
  if (body) qs.set("body", body);
  window.open(`${GHOSTMAIL_URL.replace(/\/$/, "")}/dashboard?${qs}`, "_blank", "noopener");
}
