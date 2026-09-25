// Rendre au test le stockage que Node lui reprend.
//
// ─── Le défaut, mesuré le 2026-09-25 ───
//
// Node a gagné un `localStorage`/`sessionStorage` **expérimental**, installé sur
// `globalThis` au démarrage du processus sous forme de **getter**, et qui rend
// `undefined` tant que `--localstorage-file` n'a pas été fourni :
//
//     ExperimentalWarning: localStorage is not available because
//     --localstorage-file was not provided.
//
// Ce getter occupe la place avant que l'environnement jsdom de Vitest n'installe le sien.
// Résultat : `window.localStorage` est `undefined` **aussi**, et pas seulement le global
// nu — jsdom ne redéfinit pas une propriété déjà posée. Un test qui écrit
// `localStorage.clear()` touche donc `undefined`.
//
// Sous Node 22 : 83 tests sur 83 passent. Sous Node 26.9 : onze échouent, tous sur
// « Cannot read properties of undefined ». La CI est en Node 22 (`node-version: 22` dans
// `ci.yml`), donc elle est verte — **et le restera jusqu'au jour où elle montera**.
//
// C'est une panne qui attend, et elle frappe d'abord les postes de développement. Une
// suite rouge sur la machine de celui qui code et verte en CI est la façon la plus sûre de
// lui apprendre à ne plus la lancer.
//
// ─── Le correctif ───
//
// On emprunte l'implémentation **réelle** de jsdom plutôt que d'écrire un faux stockage :
// un double maison dériverait de la vraie API sans prévenir, et les tests cesseraient de
// mesurer ce qu'ils croient mesurer. La fenêtre jetable est construite avec une `url`
// explicite — sans elle, jsdom rend une origine opaque, où le stockage n'existe pas par
// conception.
//
// `defineProperty` et non une affectation : c'est un getter qu'il faut remplacer, et lui
// affecter une valeur ne ferait rien.
//
// Le code de production n'est pas touché : dans un navigateur, `localStorage` nu est
// correct, et c'est ce qu'il doit écrire. C'est l'environnement de test qu'on répare.
import { JSDOM } from "jsdom";

const fenetre = new JSDOM("", { url: "https://tests.ghostcal.invalid" }).window;

for (const nom of ["localStorage", "sessionStorage"] as const) {
  const vrai = fenetre[nom];
  if (!vrai) continue;
  for (const cible of [globalThis, (globalThis as { window?: object }).window]) {
    if (!cible) continue;
    Object.defineProperty(cible, nom, {
      value: vrai,
      configurable: true,
      writable: true,
    });
  }
}
