import Link from "next/link";
import type { ReactNode } from "react";

/**
 * The two controls the whole product shares — 53 inputs and 27 buttons across twelve files.
 *
 * `rounded`, the charter's 12px step, and not `rounded-lg`. When the suite's radii landed,
 * `rounded-lg` went from 8px to 18px, which happened to be the value the card around these
 * controls also carried: the login screen ended up with fields as round as the panel holding
 * them, and a hierarchy that had simply flattened. A container and the things inside it should
 * not sit on the same step.
 */
export const inputClass =
  "rounded border border-border-strong bg-surface-2 px-4 py-2.5 text-sm text-foreground outline-none focus:border-accent";

export const primaryButtonClass =
  "rounded bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink shadow-[0_0_18px_color-mix(in_srgb,var(--color-accent)_45%,transparent)] transition hover:brightness-110 disabled:opacity-60";

export default function AuthCard({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <main className="flex flex-1 items-center justify-center p-4 sm:p-8">
      <div className="glass w-full max-w-sm rounded-lg p-8 shadow-2xl">
        <div className="mb-6 flex items-center gap-2 text-sm font-medium tracking-wide text-muted">
          <span className="text-accent">●</span>
          <Link href="/" className="hover:text-accent">
            GhostCal
          </Link>
        </div>
        <h1 className="text-xl font-semibold text-foreground">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
        <div className="mt-6">{children}</div>
        {footer && <div className="mt-6 text-sm text-muted">{footer}</div>}
      </div>
    </main>
  );
}
