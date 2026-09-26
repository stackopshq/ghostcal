// Ce que le serveur répond à une connexion, traduit en une décision d'écran.
//
// Le serveur envoie `mfa_required` depuis des semaines. `grep -r mfa_required frontend/src`
// rendait ZÉRO fichier : un compte dont le second facteur était activé ne pouvait plus se
// connecter au web du tout — l'écran affichait « identifiants invalides » et il n'existait
// aucun champ pour le code. Les cinq routes MFA étaient écrites, testées, migrées et
// déployées ; rien ne les lisait.
//
// La décision vit ici et non dans le composant pour deux raisons. D'abord elle s'éprouve
// sans rendu. Ensuite elle est subtile : quatre codes HTTP, dont deux 401 qui veulent dire
// des choses opposées.

/** Ce que l'écran doit faire de l'échec. */
export type SuiteDeLaConnexion =
  | { quoi: "demander-le-code" }
  | { quoi: "code-refuse" }
  | { quoi: "verrouille"; jusqua: Date | null }
  | { quoi: "identifiants-refuses" }
  | { quoi: "email-non-verifie" }
  | { quoi: "autre" };

/** La forme imbriquée que FastAPI produit : `{"detail": {"detail": …, "mfa_required": …}}`. */
interface CorpsDeDetail {
  mfa_required?: boolean;
  locked_until?: string;
}

function detailImbrique(message: string): CorpsDeDetail | null {
  try {
    const parse: unknown = JSON.parse(message);
    if (!parse || typeof parse !== "object" || !("detail" in parse))
      return null;
    const d = (parse as { detail: unknown }).detail;
    return d && typeof d === "object" ? (d as CorpsDeDetail) : null;
  } catch {
    // Une page d'erreur de proxy, par exemple. Rien à en tirer.
    return null;
  }
}

/**
 * @param codeDejaEnvoye  dit si CE client vient d'envoyer un code.
 *
 * Le serveur répond 401 + `mfa_required` dans deux cas opposés : « il me faut un code » et
 * « ce code est faux ». Il les distingue par une phrase anglaise (`two-factor code required`
 * contre `invalid two-factor code`) — et lire cette phrase ferait dépendre notre interface de
 * la prose du serveur, qu'aucun contrat ne fige. Le client sait déjà s'il a envoyé un code :
 * c'est une information plus sûre, et gratuite.
 */
export function lireLEchecDeConnexion(
  erreur: { status?: number; message?: string } | null | undefined,
  codeDejaEnvoye: boolean,
): SuiteDeLaConnexion {
  const statut = erreur?.status;
  const detail = detailImbrique(erreur?.message ?? "");

  if (statut === 429 && detail?.mfa_required) {
    // 429 et non 401 : « trop d'essais », pas « mauvais code ». Les confondre ferait
    // retaper un code à quelqu'un dont aucune saisie ne peut aboutir avant l'échéance.
    const brut = detail.locked_until;
    const date = brut ? new Date(brut) : null;
    return {
      quoi: "verrouille",
      jusqua: date && !Number.isNaN(date.getTime()) ? date : null,
    };
  }
  if (statut === 401 && detail?.mfa_required) {
    return codeDejaEnvoye
      ? { quoi: "code-refuse" }
      : { quoi: "demander-le-code" };
  }
  if (statut === 401) return { quoi: "identifiants-refuses" };
  if (statut === 403) return { quoi: "email-non-verifie" };
  return { quoi: "autre" };
}
