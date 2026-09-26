"use client";

import Link from "next/link";
import { useT } from "@/lib/i18n";
import {
  CalendarIcon,
  MailIcon,
} from "@/components/icons";
import { useEffect, useState } from "react";
import { ghostMailUrl } from "@/lib/ghostmail";

// Ghost-suite app switcher: hop between GhostCal (this app) and GhostMail (the sibling). Decoupled —
// just links, no shared backend.
//
// L'adresse du voisin est un **fait de déploiement**, et elle se demande au déploiement.
// Elle était lue dans `process.env.NEXT_PUBLIC_GHOSTMAIL_URL ?? "http://localhost:3002"` —
// c'est-à-dire le défaut exact que `lib/ghostmail.ts` documente comme corrigé, à un
// répertoire d'ici. Next grave les `NEXT_PUBLIC_*` dans le paquet à la construction : sur
// un déploiement réel, cette pastille ouvrait `http://localhost:3002` **sur la machine de
// l'utilisateur**, un onglet mort, sans rien dire. Mesuré le 2026-08-16 sur Apollo.
//
// `ghostMailUrl()` répond `null` quand ce déploiement n'a pas de GhostMail — cas courant
// pour un produit auto-hébergeable, où l'on fait tourner une application et non la suite.
// La pastille disparaît alors, plutôt que d'offrir un lien qui ne mène nulle part.

const PILL = "flex flex-1 items-center justify-center gap-1.5 rounded px-2 py-1.5 text-xs font-medium transition";

export default function SuiteSwitcher() {
  const t = useT();
  const [ghostmail, setGhostmail] = useState<string | null>(null);

  useEffect(() => {
    let vivant = true;
    void ghostMailUrl().then((u) => {
      if (vivant) setGhostmail(u);
    });
    return () => {
      vivant = false;
    };
  }, []);

  return (
    <div className="mb-4 flex gap-1 rounded-lg border border-border bg-surface-2/40 p-1">
      <Link href="/dashboard/calendar" className={`${PILL} bg-accent/15 text-accent`}>
        <CalendarIcon /> {t("suite.calendar")}
      </Link>
      {ghostmail && (
        <a href={ghostmail} className={`${PILL} text-muted hover:text-foreground`}>
          <MailIcon /> {t("suite.mail")}
        </a>
      )}
    </div>
  );
}
