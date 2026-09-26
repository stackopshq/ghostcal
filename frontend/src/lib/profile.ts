// User profile API client.

import { authedFetch, authedRequest } from "@/lib/auth";

export type Profile = {
  id: string;
  email: string;
  name: string;
  timezone: string;
  email_verified: boolean;
  avatar_url: string | null;
  /** Quand l'avatar téléversé a changé. `null` = il n'y en a pas. */
  avatar_updated_at: string | null;
};

export function getProfile(): Promise<Profile> {
  return authedFetch<Profile>("/v1/me/profile");
}

export function updateProfile(body: {
  name: string;
  timezone: string;
  avatar_url: string | null;
}): Promise<Profile> {
  return authedFetch<Profile>("/v1/me/profile", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

/** Le poids qu'accepte le serveur, avant ré-encodage. Voir `application/avatars.py`. */
export const AVATAR_OCTETS_MAX = 2 * 1024 * 1024;

/** Téléverse une image d'avatar.
 *
 * Le serveur la **ré-encode** en WebP et la borne à 512 px : ce qui part n'est pas ce qui
 * est stocké. Il refuse en 422 avec un motif lisible — « fichier vide », « format non
 * reconnu » — et c'est ce motif qu'il faut montrer, pas un « erreur » générique.
 */
export function uploadAvatar(fichier: File): Promise<void> {
  const corps = new FormData();
  corps.append("fichier", fichier);
  return authedFetch<void>("/v1/me/profile/avatar", { method: "POST", body: corps });
}

/** Retire l'avatar téléversé. Le champ `avatar_url`, lui, est un réglage distinct. */
export function removeAvatar(): Promise<void> {
  return authedFetch<void>("/v1/me/profile/avatar", { method: "DELETE" });
}

export function changePassword(body: {
  current_password: string;
  new_password: string;
}): Promise<void> {
  return authedFetch<void>("/v1/me/profile/password", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Charge l'avatar téléversé et rend une URL d'objet, à révoquer par l'appelant.
 *
 * ─── Pourquoi ce détour plutôt qu'un `<img src="…">` ───
 *
 * La route `GET /v1/me/profile/avatar/{id}` exige `current_member`, donc un en-tête
 * `Authorization: Bearer`. Un `<img>` n'en envoie **jamais** : le navigateur ne pose
 * que les cookies. L'image partait donc en 401, `onError` se déclenchait, et l'écran
 * retombait sur les initiales — exactement comme si aucun avatar n'avait été
 * téléversé. Le téléversement, lui, réussissait.
 *
 * Et l'adresse construite à la main oubliait le préfixe de l'API : elle demandait
 * `/v1/me/profile/avatar/…` à l'application Next, qui rend 404. Deux raisons
 * indépendantes, chacune suffisante, d'où l'absence de toute trace côté serveur.
 *
 * `authedRequest` apporte le jeton, le préfixe et le rafraîchissement sur 401.
 */
export async function chargerAvatar(userId: string): Promise<string> {
  const res = await authedRequest(`/v1/me/profile/avatar/${userId}`);
  return URL.createObjectURL(await res.blob());
}
