"use client";

import Link from "next/link";
import { useT } from "@/lib/i18n";

// Minimal landing. The real booking experience lives at /{org}/{event}.
const DEMO_PATH = process.env.NEXT_PUBLIC_DEMO_PATH;

export default function Home() {
  const t = useT();
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 p-8 text-center">
      <div className="flex items-center gap-3">
        <span className="text-3xl text-accent">●</span>
        <h1 className="text-4xl font-semibold tracking-tight text-foreground">GhostCal</h1>
      </div>
      <p className="max-w-md text-muted">{t("landing.tagline")}</p>
      <div className="flex flex-wrap items-center justify-center gap-3">
        <Link
          href="/register"
          className="rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-accent-ink shadow-[0_0_18px_color-mix(in_srgb,var(--color-accent)_45%,transparent)] transition hover:brightness-110"
        >
          {t("landing.getStarted")}
        </Link>
        <Link
          href="/login"
          className="rounded-lg border border-border-strong px-5 py-2.5 text-sm font-medium text-foreground transition hover:border-accent hover:text-accent"
        >
          {t("common.signIn")}
        </Link>
      </div>
      {DEMO_PATH && (
        <Link href={DEMO_PATH} className="text-sm text-muted hover:text-accent">
          {t("landing.tryDemo")}
        </Link>
      )}
    </main>
  );
}
