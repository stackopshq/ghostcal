"use client";

import { useT } from "@/lib/i18n";

// Bascule le thème sur <html> et le retient.
//
// **Aucun état React**, volontairement : l'icône visible est décidée par le CSS depuis
// l'attribut `data-theme` (voir `globals.css`). Lire `localStorage` dans un effet pour
// en déduire un état ferait diverger le rendu serveur du rendu client — donc une
// hydratation en conflit, et un clignotement au chargement pour qui a choisi le clair.
//
// Le libellé accessible suit le même chemin. Chaque icône porte son propre texte
// `sr-only`, et celle qui n'est pas affichée est en `display: none` — donc retirée de
// l'arbre d'accessibilité. Le nom du bouton change ainsi avec le thème sans qu'une
// seule ligne de JavaScript ne s'en occupe. C'est ce qui permet de se passer
// d'`aria-pressed`, qui aurait exigé l'état qu'on vient d'éviter.
const commun = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  className: "size-4",
  "aria-hidden": true,
};

export default function ThemeToggle({ className = "" }: { className?: string }) {
  const t = useT();

  function toggle() {
    const root = document.documentElement;
    const next = root.dataset.theme === "light" ? "dark" : "light";
    root.dataset.theme = next;
    try {
      localStorage.setItem("gc_theme", next);
    } catch {
      /* Un navigateur qui refuse le stockage garde quand même le thème pour la
         session en cours : l'attribut est déjà posé. Seule la mémoire d'une visite
         à l'autre est perdue, et c'est préférable à une bascule qui échoue. */
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      className={`cursor-pointer rounded-full p-1 text-muted transition-colors hover:text-foreground ${className}`}
    >
      {/* Le soleil en thème sombre : il dit où l'on va, pas où l'on est. */}
      <span className="theme-icon-sun">
        <svg {...commun}>
          <circle cx="12" cy="12" r="4" />
          <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4" />
        </svg>
        <span className="sr-only">{t("app.lightMode")}</span>
      </span>
      <span className="theme-icon-moon">
        <svg {...commun}>
          <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z" />
        </svg>
        <span className="sr-only">{t("app.darkMode")}</span>
      </span>
    </button>
  );
}
