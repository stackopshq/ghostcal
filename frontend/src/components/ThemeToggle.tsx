"use client";

import { MoonIcon, SunIcon } from "@/components/icons";
import { useT } from "@/lib/i18n";

// Bascule le thème sur <html> et le retient.
//
// **Aucun état React**, volontairement : l'icône visible est décidée par le CSS depuis
// l'attribut `data-theme` (voir `globals.css`). Lire `localStorage` dans un effet pour
// en déduire un état ferait diverger le rendu serveur du rendu client — donc une
// hydratation en conflit, et un clignotement au chargement pour qui a choisi le clair.
//
// Le libellé accessible suit le même chemin. Chaque porteuse porte son propre texte
// `sr-only`, et celle qui n'est pas affichée est en `display: none` — donc retirée de
// l'arbre d'accessibilité. Le nom du bouton change ainsi avec le thème sans une seule
// ligne de JavaScript. C'est ce qui permet de se passer d'`aria-pressed`, qui aurait
// exigé l'état qu'on vient d'éviter.
//
// Les libellés étaient écrits en anglais, en dur, dans une application bilingue — et
// `aria-hidden` sur les porteuses achevait de rendre le bouton muet pour un lecteur
// d'écran. Voir le §0 de la charte : ce qui se traduit inclut ce qui ne se lit pas.
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
      className={`cursor-pointer text-sm leading-none transition hover:opacity-80 ${className}`}
    >
      {/* Le soleil en thème sombre : il dit où l'on va, pas où l'on est. */}
      <span className="theme-icon-sun">
        <SunIcon aria-hidden />
        <span className="sr-only">{t("app.lightMode")}</span>
      </span>
      <span className="theme-icon-moon">
        <MoonIcon aria-hidden />
        <span className="sr-only">{t("app.darkMode")}</span>
      </span>
    </button>
  );
}
