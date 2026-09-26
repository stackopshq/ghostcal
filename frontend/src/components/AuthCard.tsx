"use client";

import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { getAuthConfig } from "@/lib/auth";
import { useT } from "@/lib/i18n";

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
  "w-full rounded border border-border bg-surface-2 px-3.5 py-2.5 text-sm text-foreground " +
  "placeholder:text-muted focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25";

/**
 * Un champ étiqueté — la structure de `Champ` chez ghostpass, à l'identique.
 *
 * GhostCal posait ses libellés en `placeholder`. Ce n'est pas la même chose :
 * un placeholder disparaît dès la première frappe, il n'est pas rattaché au
 * champ pour un lecteur d'écran, et le formulaire vide et le formulaire rempli
 * ne portent pas la même information. Les deux écrans se distinguaient donc à
 * l'œil ET à l'oreille.
 */
export function Champ({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-muted">{label}</span>
      {children}
    </label>
  );
}

/**
 * Le pied de carte : la question reste du TEXTE, seule l'action est un lien.
 *
 * La charte (§6) porte ce défaut, mesuré sur ghostpass : quand la phrase
 * entière est l'action, en `text-muted`, son unique signal d'interactivité est
 * `hover:` — un état qu'un écran tactile n'atteint jamais. GhostCal le portait
 * encore : « Mot de passe oublié » était un `text-muted hover:text-accent` sur
 * une ligne nue, indiscernable d'un gris inerte sur téléphone.
 */
export const lienDePied =
  "font-medium text-accent underline underline-offset-2 transition hover:brightness-125";

export const primaryButtonClass =
  "rounded-pill bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink shadow-[0_0_18px_color-mix(in_srgb,var(--color-accent)_45%,transparent)] transition hover:brightness-110 disabled:opacity-60";

// Vers quoi pointe « Politique de confidentialité ».
//
// La page de la suite couvre tous les produits et porte une section GhostCal nommée.
// Elle est juste pour une instance hébergée par StackOps, et **fausse pour une
// instance auto-hébergée** : là, le responsable du traitement est l'hébergeur, et le
// renvoyer vers notre texte lui ferait endosser des engagements qu'il n'a pas pris.
//
// **L'adresse vient donc du serveur**, jamais d'une `NEXT_PUBLIC_*`. Next grave
// celles-ci dans le paquet à la construction : l'auto-hébergeur tire l'image publiée,
// poser la variable chez lui ne changerait rien, et rien ne le lui dirait. C'est
// exactement l'incident mesuré le 2026-08-16 sur Apollo, dont `ghostmail.ts` porte le
// récit — et j'avais réintroduit le motif ici avant qu'on me le fasse remarquer.
//
// Cette constante n'est plus qu'un **repli d'affichage**, le temps que la requête
// revienne et pour le cas où elle échoue : mieux vaut la page de la suite qu'un lien
// absent.
const PRIVACY_PAR_DEFAUT = "https://ghostsuite.cloud/confidentialite/";

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

  // Demandée au déploiement, comme le bouton SSO l'est déjà (voir `getAuthConfig`).
  // L'échec ne fait pas disparaître le lien : il retombe sur la page de la suite,
  // juste pour la grande majorité des instances.
  const [privacyUrl, setPrivacyUrl] = useState(PRIVACY_PAR_DEFAUT);
  useEffect(() => {
    let vivant = true;
    getAuthConfig()
      .then((c) => {
        if (vivant && c.privacy_url) setPrivacyUrl(c.privacy_url);
      })
      .catch(() => {
        /* `getAuthConfig` journalise déjà le code HTTP. */
      });
    return () => {
      vivant = false;
    };
  }, []);

  return (
    <main className="grid min-h-dvh place-items-center px-4 py-10">
      <div className="w-full max-w-[420px]">
        {/* La marque au-dessus de la carte, à sa taille de page d'accueil — la même
            structure que GhostPass, qui fait référence. Elle était auparavant réduite
            à une ligne discrète *dans* l'en-tête de la carte, à côté d'un « ● » : le
            seul écran par lequel tout le monde entre était donc celui où le produit
            ne se présentait pas. */}
        <div className="mb-7 flex flex-col items-center gap-3">
          {/* `ghost-mark` : la pastille sombre que la charte pose derrière la
              marque. Le dégradé du logo de GhostCal va d'un cyan clair à un cyan
              profond ; sur le fond clair de ce mode il mesurait 1,12:1, le
              deuxième pire des huit. La pastille vaut le `base` du thème SOMBRE
              dans les deux thèmes : en sombre elle se confond avec la page et ne
              se voit pas, en clair elle apparaît et porte le logo. */}
          <span className="ghost-mark">
            <Image src="/logo.svg" alt="" width={44} height={44} className="size-11" priority />
          </span>
          <Link
            href="/login"
            className="text-2xl font-semibold tracking-tight text-foreground transition hover:text-accent"
          >
            GhostCal
          </Link>
        </div>

        {/* `verre` et non `glass` : voir la note de `globals.css`. Et `p-6`, le
            retrait de ghostpass — `p-8` décalait de 8 px tout ce que la carte
            contient, ce qui suffit à faire deux écrans qu'on ne superpose pas. */}
        <section className="verre rounded-lg border border-border p-6">
          <h1 className="mb-4 text-lg font-semibold text-foreground">{title}</h1>
          {subtitle && <p className="-mt-2 mb-3 text-sm text-muted">{subtitle}</p>}
          {children}
          {footer && <div className="mt-4 text-xs text-muted">{footer}</div>}
        </section>

        {/* La promesse du produit, là où l'on décide d'y entrer.
            **Et non « zero-knowledge », qui serait faux ici.** GhostPass porte cette
            mention parce qu'il ne peut rien lire ; GhostCal doit lire ce qu'il
            organise pour proposer un créneau, et sa propre politique de
            confidentialité le dit sans détour.

            La phrase disait « Titres d'évènements chiffrés ». C'était exact et
            illisible : personne ne se demande, devant un écran de connexion, ce
            qu'est un titre d'évènement par opposition au reste. Elle nomme
            désormais la chose (« le contenu de vos évènements ») et l'endroit
            (« sur votre appareil »), qui est la partie qui compte pour qui lit.

            Elle reste plus modeste que celle de GhostPass, et c'est voulu :
            recopier la promesse du frère serait la seule façon de rater cette
            harmonisation. */}
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
          <span>{t("auth.promise")}</span>
        </div>

        {/* Atteignable sans avoir à créer un compte : quelqu'un qui revient se
            connecter doit pouvoir relire ce à quoi il a consenti. C'est la raison
            pour laquelle ce lien vit ici et non dans le seul formulaire
            d'inscription. */}
        <p className="mt-3 text-center">
          <a
            href={privacyUrl}
            className="text-xs text-muted underline underline-offset-2 transition hover:text-foreground"
          >
            {t("auth.privacyPolicy")}
          </a>
        </p>
      </div>
    </main>
  );
}
