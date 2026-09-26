"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { inputClass, primaryButtonClass } from "@/components/AuthCard";
import { ApiError } from "@/lib/api";
import { logout, rewrapAllForNewPassword } from "@/lib/auth";
import { useT } from "@/lib/i18n";
import {
  AVATAR_OCTETS_MAX,
  changePassword,
  getProfile,
  removeAvatar,
  updateProfile,
  uploadAvatar,
  chargerAvatar,
} from "@/lib/profile";
import { MIN_PASSWORD_LENGTH } from "@/lib/passwords";

/** Les initiales, dessinées ici — aucun réseau, aucun tiers.
 *
 * Le repli précédent allait chercher `api.dicebear.com`, et la politique de
 * sécurité de contenu n'autorise que `'self' data: blob:` : **aucun avatar ne
 * s'est jamais affiché**, pas même celui par défaut. Le cercle vide n'était
 * pas l'échec d'une URL, c'était l'absence de toute image.
 *
 * Aller chercher un service tiers pour dessiner deux lettres contredisait de
 * toute façon la promesse du produit — « le serveur sait quand vous êtes
 * occupé, jamais pourquoi » ne tient pas si un tiers apprend qui regarde quoi,
 * et à quelle heure.
 */
function Avatar({
  url,
  name,
  broken,
  onBroken,
}: {
  url: string;
  name: string;
  broken: boolean;
  onBroken: () => void;
}) {
  const initials =
    name
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((w) => w[0] ?? "")
      .join("")
      .toUpperCase() || "?";

  if (url && !broken) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={url}
        alt=""
        onError={onBroken}
        className="h-14 w-14 shrink-0 rounded-pill border border-border-strong object-cover"
      />
    );
  }
  return (
    <span
      aria-hidden
      className="flex h-14 w-14 shrink-0 items-center justify-center rounded-pill border border-border-strong bg-surface-2 text-lg font-semibold text-muted"
    >
      {initials}
    </span>
  );
}

function timezones(fallback: string): string[] {
  const fn = (Intl as { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf;
  try {
    return fn ? fn("timeZone") : [fallback];
  } catch {
    return [fallback];
  }
}

export default function ProfileSettings() {
  const t = useT();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [tz, setTz] = useState("UTC");
  const [avatar, setAvatar] = useState("");
  const [avatarBroken, setAvatarBroken] = useState(false);
  // L'horodatage de l'avatar téléversé, ou `null` s'il n'y en a pas.
  //
  // Il sert deux fois : décider si l'on affiche l'image ou les initiales, et **casser le
  // cache** de l'image après un envoi. Sans le second usage, le navigateur continuerait
  // d'afficher l'ancienne — un téléversement qui paraît n'avoir rien fait.
  const [avatarPose, setAvatarPose] = useState<string | null>(null);
  const [profilId, setProfilId] = useState("");
  const [avatarOccupe, setAvatarOccupe] = useState(false);
  const [avatarErreur, setAvatarErreur] = useState<string | null>(null);
  const fichierRef = useRef<HTMLInputElement>(null);
  const zones = useMemo(() => timezones("UTC"), []);
  const [savedProfile, setSavedProfile] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [savedPassword, setSavedPassword] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getProfile()
      .then((p) => {
        if (!active) return;
        setEmail(p.email);
        setName(p.name);
        setTz(p.timezone);
        setAvatar(p.avatar_url ?? "");
        setAvatarPose(p.avatar_updated_at);
        setProfilId(p.id);
      })
      .catch(() => active && setProfileError(t("profile.errLoad")));
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** L'image téléversée, chargée AVEC le jeton, puis tenue en URL d'objet.
   *
   * Ce n'était qu'une adresse posée dans `src` — et un `<img>` n'envoie pas
   * d'en-tête `Authorization`. La route en exige un ; l'image partait donc en
   * 401, `onError` se déclenchait, et l'écran retombait sur les initiales comme
   * si rien n'avait été téléversé. L'adresse oubliait de surcroît le préfixe de
   * l'API et visait l'application Next, qui rend 404.
   *
   * Plus d'empreinte `?v=` : `avatarPose` change à chaque téléversement, donc
   * cet effet rejoue et refait une URL d'objet neuve. Il n'y a pas de cache
   * navigateur à déjouer, l'octet vient d'ici.
   */
  // L'URL d'objet est retenue AVEC la version qu'elle montre. Sans cela, retirer
  // l'avatar puis en téléverser un autre afficherait l'ancien — déjà révoqué,
  // donc cassé — pendant le chargement du nouveau.
  const [blobAvatar, setBlobAvatar] = useState<{ pose: string; url: string } | null>(null);

  useEffect(() => {
    if (!avatarPose || !profilId) return;
    let actif = true;
    // Révoquée au démontage : une URL d'objet retient son blob en mémoire tant
    // que personne ne la relâche, et l'écran en fabrique une à chaque changement.
    let aRevoquer = "";
    const pose = avatarPose;
    chargerAvatar(profilId)
      .then((u) => {
        if (!actif) {
          URL.revokeObjectURL(u);
          return;
        }
        aRevoquer = u;
        setBlobAvatar({ pose, url: u });
        setAvatarBroken(false);
      })
      .catch(() => {
        if (actif) setBlobAvatar(null);
      });
    return () => {
      actif = false;
      if (aRevoquer) URL.revokeObjectURL(aRevoquer);
    };
  }, [avatarPose, profilId]);

  const urlAvatarPose =
    blobAvatar && blobAvatar.pose === avatarPose ? blobAvatar.url : "";

  async function televerser(fichier: File) {
    setAvatarErreur(null);
    // Le poids se vérifie ici AUSSI, alors que le serveur le fait déjà. Un aller-retour
    // de deux mégaoctets pour s'entendre dire « trop gros » est une attente qu'on peut
    // éviter, et le message arrive instantanément.
    if (fichier.size > AVATAR_OCTETS_MAX) {
      setAvatarErreur(t("profile.avatarTooBig"));
      return;
    }
    setAvatarOccupe(true);
    try {
      await uploadAvatar(fichier);
      const frais = await getProfile();
      setAvatarPose(frais.avatar_updated_at);
      setAvatarBroken(false);
    } catch (err) {
      // Le serveur refuse en 422 avec un motif lisible — « format non reconnu »,
      // « fichier vide ». C'est CE motif qu'il faut montrer : « erreur » n'aide
      // personne à choisir une autre image.
      setAvatarErreur(
        err instanceof ApiError && err.detail ? err.detail : t("profile.avatarErr"),
      );
    } finally {
      setAvatarOccupe(false);
    }
  }

  async function retirerAvatar() {
    setAvatarErreur(null);
    setAvatarOccupe(true);
    try {
      await removeAvatar();
      setAvatarPose(null);
    } catch {
      setAvatarErreur(t("profile.avatarErr"));
    } finally {
      setAvatarOccupe(false);
    }
  }

  async function saveProfile(e: React.FormEvent) {
    e.preventDefault();
    setProfileError(null);
    setSavedProfile(false);
    try {
      await updateProfile({ name, timezone: tz, avatar_url: avatar.trim() || null });
      setSavedProfile(true);
    } catch {
      setProfileError(t("profile.errSave"));
    }
  }

  async function savePassword(e: React.FormEvent) {
    e.preventDefault();
    setPasswordError(null);
    setSavedPassword(false);
    let rewrapFailed = false;
    try {
      await changePassword({ current_password: current, new_password: next });

      // Ré-envelopper les clés d'organisation sous le NOUVEAU mot de passe, et
      // le faire ICI — après le changement, avant la déconnexion.
      //
      // La clé privée d'organisation est enveloppée sous une clé dérivée du mot
      // de passe. Le serveur ne peut pas la ré-envelopper : il ne voit jamais la
      // clé privée, c'est tout l'objet du zero-knowledge. Si le client ne le
      // fait pas, l'enveloppe reste scellée sous l'ANCIEN mot de passe et la
      // connexion suivante ne peut plus l'ouvrir : on entre, l'authentification
      // marche, et l'agenda est vide. Les données ne sont pas perdues, elles
      // sont définitivement illisibles — ce qui revient au même.
      //
      // L'ordre n'est pas négociable. Avant `changePassword`, on n'a pas encore
      // le droit d'écrire les nouvelles enveloppes ; après `logout`,
      // `clearUnlockedKeys` a effacé les clés déverrouillées et il n'y a plus
      // rien à ré-envelopper. La fenêtre est exactement ici.
      rewrapFailed = true;
      await rewrapAllForNewPassword(next);
      rewrapFailed = false;

      setCurrent("");
      setNext("");
      setSavedPassword(true);
      // The server has just revoked every refresh token, this tab's included — that is the point
      // of changing a password. The access token would keep working for its last few minutes and
      // then fail mid-action, so end the session here and say why, rather than letting it rot.
      await logout();
      window.location.assign("/login?reason=password-changed");
    } catch (err) {
      // Un échec APRÈS le changement de mot de passe est d'une autre nature : le
      // mot de passe a changé mais les enveloppes non, donc le compte est
      // exactement dans l'état que ce correctif existe pour éviter. On ne
      // déconnecte pas — tant que la session vit, les clés déverrouillées sont
      // encore en mémoire et un nouvel essai peut réussir. Déconnecter ici
      // rendrait la panne irréversible.
      if (rewrapFailed) {
        setPasswordError(t("profile.errRewrap"));
        return;
      }
      setPasswordError(
        err instanceof ApiError && err.status === 403
          ? t("profile.errCurrentWrong")
          : err instanceof ApiError && err.status === 422
            ? err.detail || t("profile.errPassword")
            : t("profile.errPassword"),
      );
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <h2 className="text-lg font-semibold text-foreground">{t("profile.yourProfile")}</h2>

      <form onSubmit={saveProfile} className="flex flex-col gap-4">
        {/* Le téléversement, enfin offert.
            L'API l'accepte depuis le 2026-09-25 — POST, DELETE, et une route qui sert
            l'image — mais aucun écran ne l'exposait. Le champ URL ci-dessous était le
            seul chemin proposé, et il ne mène nulle part : la politique de sécurité de
            contenu n'autorise que les images de ce site, donc une adresse externe est
            refusée par le navigateur. Le seul chemin qui marche est celui qu'on ne
            montrait pas. */}
        <div className="flex items-center gap-4">
          <Avatar
            url={urlAvatarPose || avatar}
            name={name}
            broken={avatarBroken}
            onBroken={() => setAvatarBroken(true)}
          />
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <input
                ref={fichierRef}
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  // La valeur est vidée pour que rechoisir LE MÊME fichier redéclenche
                  // l'évènement : sans cela, une seconde tentative après un refus ne
                  // ferait rien, et l'écran paraîtrait figé.
                  e.target.value = "";
                  if (f) void televerser(f);
                }}
              />
              <button
                type="button"
                onClick={() => fichierRef.current?.click()}
                disabled={avatarOccupe}
                className={primaryButtonClass}
              >
                {avatarOccupe ? t("profile.avatarBusy") : t("profile.avatarUpload")}
              </button>
              {avatarPose && (
                <button
                  type="button"
                  onClick={() => void retirerAvatar()}
                  disabled={avatarOccupe}
                  className="rounded-pill border border-border-strong px-4 py-2.5 text-sm text-muted transition hover:text-foreground"
                >
                  {t("profile.avatarRemove")}
                </button>
              )}
            </div>
            <span className="text-xs text-muted">{t("profile.avatarHint")}</span>
            {avatarErreur && <span className="text-xs text-danger">{avatarErreur}</span>}
          </div>
        </div>

        {/* Le champ URL reste, mais en repli et dit pour ce qu'il est : il ne sert que
            pour une adresse servie par ce site. */}
        <details className="text-sm text-muted">
          <summary className="cursor-pointer">{t("profile.avatarUrlToggle")}</summary>
          <label className="mt-2 flex min-w-0 flex-col gap-1">
            <input
              type="url"
              placeholder="https://…/avatar.png"
              value={avatar}
              onChange={(e) => {
                setAvatar(e.target.value);
                setAvatarBroken(false);
              }}
              className={inputClass}
            />
            {avatarBroken && (
              // Le champ acceptait et enregistrait une URL qui ne pouvait pas
              // s'afficher, sans rien dire : la politique de sécurité de contenu
              // n'autorise que les images de ce site. Un champ qui ment est pire
              // qu'un champ qui refuse.
              <span className="text-xs text-danger">{t("profile.avatarBlocked")}</span>
            )}
          </label>
        </details>
        <label className="flex flex-col gap-1 text-sm text-muted">
          {t("common.email")}
          <input value={email} disabled className={`${inputClass} opacity-60`} />
        </label>
        <label className="flex flex-col gap-1 text-sm text-muted">
          {t("profile.name")}
          <input value={name} onChange={(e) => setName(e.target.value)} className={inputClass} />
        </label>
        <label className="flex flex-col gap-1 text-sm text-muted">
          {t("profile.timezone")}
          <select value={tz} onChange={(e) => setTz(e.target.value)} className={inputClass}>
            {zones.map((z) => (
              <option key={z} value={z}>
                {z}
              </option>
            ))}
          </select>
        </label>
        {profileError && <p className="text-sm text-red-400">{profileError}</p>}
        <div className="flex items-center gap-4">
          <button type="submit" className={primaryButtonClass}>
            {t("profile.save")}
          </button>
          {savedProfile && <span className="text-sm text-accent">{t("common.saved")}</span>}
        </div>
      </form>

      <form onSubmit={savePassword} className="flex flex-col gap-4 border-t border-border pt-6">
        <h3 className="text-sm font-medium text-foreground">{t("profile.changePassword")}</h3>
        <input
          type="password"
          required
          placeholder={t("profile.currentPassword")}
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          className={inputClass}
        />
        <input
          type="password"
          required
          minLength={MIN_PASSWORD_LENGTH}
          placeholder={t("profile.newPassword")}
          value={next}
          onChange={(e) => setNext(e.target.value)}
          className={inputClass}
        />
        {passwordError && <p className="text-sm text-red-400">{passwordError}</p>}
        <div className="flex items-center gap-4">
          <button type="submit" className={primaryButtonClass}>
            {t("profile.updatePassword")}
          </button>
          {savedPassword && <span className="text-sm text-accent">{t("profile.updated")}</span>}
        </div>
      </form>
    </div>
  );
}
