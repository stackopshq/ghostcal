// "Email guests" bridge to GhostMail (the sibling mail app). Fully decoupled, the mirror of
// GhostMail's "Add to calendar": we hand GhostMail a compose deep-link (recipients + subject) and
// it opens its composer prefilled. GhostCal never calls GhostMail's backend; the message is written
// and encrypted entirely in the GhostMail session.

// Where GhostMail lives. Configurable per deployment; sensible dev default.
const GHOSTMAIL_URL = process.env.NEXT_PUBLIC_GHOSTMAIL_URL ?? "http://localhost:3002";

/** Open GhostMail's composer prefilled with recipients and a subject (the user reviews and sends). */
export function openInGhostMail({ to, subject }: { to: string[]; subject: string }): void {
  const qs = new URLSearchParams({ compose: "1", to: to.join(","), subject });
  window.open(`${GHOSTMAIL_URL.replace(/\/$/, "")}/dashboard?${qs}`, "_blank", "noopener");
}
