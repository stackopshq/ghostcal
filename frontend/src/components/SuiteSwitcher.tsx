"use client";

import Link from "next/link";
import { useT } from "@/lib/i18n";

// Ghost-suite app switcher: hop between GhostCal (this app) and GhostMail (the sibling). Decoupled —
// just links, no shared backend. The sibling URL is per-deployment.
const GHOSTMAIL_URL = process.env.NEXT_PUBLIC_GHOSTMAIL_URL ?? "http://localhost:3002";

const PILL = "flex flex-1 items-center justify-center gap-1.5 rounded px-2 py-1.5 text-xs font-medium transition";

export default function SuiteSwitcher() {
  const t = useT();
  return (
    <div className="mb-4 flex gap-1 rounded-lg border border-border bg-surface-2/40 p-1">
      <Link href="/dashboard/calendar" className={`${PILL} bg-accent/15 text-accent`}>
        <span aria-hidden>📅</span> {t("suite.calendar")}
      </Link>
      <a href={GHOSTMAIL_URL} className={`${PILL} text-muted hover:text-foreground`}>
        <span aria-hidden>✉️</span> {t("suite.mail")}
      </a>
    </div>
  );
}
