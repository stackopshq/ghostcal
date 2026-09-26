// Quel écran montrer, et quand s'inquiéter du stock de codes.
//
// Deux décisions que l'on met d'ordinaire dans du JSX, où elles deviennent intestables sans
// rendu complet — c'est le défaut que la charte nomme, et il a déjà coûté un bouton
// « Activer la 2FA » affiché à quelqu'un qui l'avait déjà activée, sur GhostPass.

import type { EtatDuSecondFacteur } from "@/lib/auth";

export type EtapeDuSecondFacteur =
  "chargement" | "codes-a-noter" | "enrolement" | "actif" | "inactif";

/**
 * L'ordre des cas EST la décision.
 *
 * Les codes de récupération passent devant tout : c'est le seul instant où le serveur les
 * rend lisibles — seules leurs empreintes sont gardées, donc ni le support ni nous ne
 * pourrons les réafficher. Les montrer après une bascule d'état, ou sous un formulaire, c'est
 * les faire fermer sans être notés.
 *
 * `pending` est un enrôlement commencé et jamais activé. Il ne protège RIEN : la ligne existe
 * en base, mais aucune porte n'est gardée tant que `/mfa/activate` n'a pas reçu un premier
 * code juste. Le traiter comme « actif » annoncerait une protection inexistante.
 */
export function etapeDuSecondFacteur(
  etat: EtatDuSecondFacteur | null,
  enrolementEnCours: boolean,
  codesARemettre: boolean,
): EtapeDuSecondFacteur {
  if (codesARemettre) return "codes-a-noter";
  if (etat === null) return "chargement";
  if (enrolementEnCours) return "enrolement";
  if (etat.enabled) return "actif";
  return "inactif";
}

/// En dessous, la réserve s'épuise — le moment où l'on se croit protégé sans porte de sortie.
export const CODES_RESTANTS_INQUIETANTS = 3;

export function resteDeCodesInquietant(restants: number): boolean {
  return restants <= CODES_RESTANTS_INQUIETANTS;
}
