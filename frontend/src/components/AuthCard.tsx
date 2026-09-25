import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";

export const inputClass =
  "rounded-lg border border-border-strong bg-surface-2 px-4 py-2.5 text-sm text-foreground outline-none focus:border-accent";

export const primaryButtonClass =
  "rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink shadow-[0_0_18px_rgba(0,240,255,0.45)] transition hover:brightness-110 disabled:opacity-60";

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
      <div className="glass w-full max-w-sm rounded-2xl p-8 shadow-2xl">
        {/* Le logo de la charte, et non le rond qui tenait sa place.
            `public/logo.svg` existe depuis le début et sert déjà dans le tableau de bord :
            la marque n'apparaissait donc qu'**après** la connexion, là où elle a le moins
            à prouver, et un point cyan accueillait les nouveaux venus. */}
        <div className="mb-6 flex items-center gap-2 text-sm font-medium tracking-wide text-muted">
          <Image src="/logo.svg" alt="" width={20} height={20} className="h-5 w-5" priority />
          <Link href="/login" className="hover:text-accent">
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
