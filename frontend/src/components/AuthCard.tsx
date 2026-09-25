"use client";

import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";
import { useT } from "@/lib/i18n";

export const inputClass =
  "rounded-lg border border-border-strong bg-surface-2 px-4 py-2.5 text-sm text-foreground outline-none focus:border-accent";

export const primaryButtonClass =
  "rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink shadow-[0_0_18px_rgba(0,240,255,0.45)] transition hover:brightness-110 disabled:opacity-60";

// Vers quoi pointe « Politique de confidentialité ».
//
// La page couvre toute la suite et porte une section GhostCal nommée, qui dit ce que
// le serveur voit. Elle est donc juste pour une instance hébergée par StackOps.
//
// **Elle ne l'est pas pour une instance auto-hébergée** : là, c'est l'hébergeur qui
// est responsable du traitement, pas nous, et le renvoyer vers notre page serait lui
// faire endosser un texte qui n'est pas le sien. D'où la dérogation par variable,
// comme `NEXT_PUBLIC_SITE_URL` pour l'origine des aperçus.
const PRIVACY_URL =
  process.env.NEXT_PUBLIC_PRIVACY_URL ?? "https://ghostsuite.cloud/confidentialite/";

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
  const t = useT();
  return (
    <main className="grid min-h-dvh place-items-center px-4 py-10">
      <div className="w-full max-w-[420px]">
        {/* La marque au-dessus de la carte, à sa taille de page d'accueil — la même
            structure que GhostPass, qui fait référence. Elle était auparavant réduite
            à une ligne discrète *dans* l'en-tête de la carte, à côté d'un « ● » : le
            seul écran par lequel tout le monde entre était donc celui où le produit
            ne se présentait pas. */}
        <div className="mb-7 flex flex-col items-center gap-3">
          <Image src="/logo.svg" alt="" width={44} height={44} className="size-11" priority />
          <Link
            href="/login"
            className="text-2xl font-semibold tracking-tight text-foreground transition hover:text-accent"
          >
            GhostCal
          </Link>
        </div>

        <section className="glass rounded-2xl p-8 shadow-2xl">
          <h1 className="text-xl font-semibold text-foreground">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
          <div className="mt-6">{children}</div>
          {footer && <div className="mt-6 text-sm text-muted">{footer}</div>}
        </section>

        {/* La promesse du produit, là où l'on décide d'y entrer.
            **Et non « zero-knowledge », qui serait faux ici.** GhostPass porte cette
            mention parce qu'il ne peut rien lire ; GhostCal doit lire ce qu'il
            organise pour proposer un créneau, et sa propre politique de
            confidentialité le dit sans détour. Ce qu'il chiffre vraiment, ce sont les
            titres. C'est plus modeste, et c'est vrai — recopier la promesse du frère
            aurait été la seule façon de rater cette harmonisation. */}
        <div className="mt-6 flex items-center justify-center gap-1.5 text-xs text-muted">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.8}
            strokeLinecap="round"
            strokeLinejoin="round"
            className="size-3.5"
            aria-hidden="true"
          >
            <rect x="4" y="10" width="16" height="10" rx="2" />
            <path d="M8 10V7a4 4 0 0 1 8 0v3" />
          </svg>
          <span>{t("auth.encryptedTitles")}</span>
        </div>

        {/* Atteignable sans avoir à créer un compte : quelqu'un qui revient se
            connecter doit pouvoir relire ce à quoi il a consenti. C'est la raison
            pour laquelle ce lien vit ici et non dans le seul formulaire
            d'inscription. */}
        <p className="mt-3 text-center">
          <a
            href={PRIVACY_URL}
            className="text-xs text-muted underline underline-offset-2 transition hover:text-foreground"
          >
            {t("auth.privacyPolicy")}
          </a>
        </p>
      </div>
    </main>
  );
}
