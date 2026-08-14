"use client";

import { useEffect, useMemo, useState } from "react";
import { inputClass, primaryButtonClass } from "@/components/AuthCard";
import { ApiError } from "@/lib/api";
import { logout } from "@/lib/auth";
import { useT } from "@/lib/i18n";
import { changePassword, getProfile, updateProfile } from "@/lib/profile";
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
        className="h-14 w-14 shrink-0 rounded-full border border-border-strong object-cover"
      />
    );
  }
  return (
    <span
      aria-hidden
      className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full border border-border-strong bg-surface-2 text-lg font-semibold text-muted"
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
      })
      .catch(() => active && setProfileError(t("profile.errLoad")));
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
    try {
      await changePassword({ current_password: current, new_password: next });
      setCurrent("");
      setNext("");
      setSavedPassword(true);
      // The server has just revoked every refresh token, this tab's included — that is the point
      // of changing a password. The access token would keep working for its last few minutes and
      // then fail mid-action, so end the session here and say why, rather than letting it rot.
      await logout();
      window.location.assign("/login?reason=password-changed");
    } catch (err) {
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
        <div className="flex items-center gap-4">
          <Avatar
            url={avatar}
            name={name}
            broken={avatarBroken}
            onBroken={() => setAvatarBroken(true)}
          />
          <label className="flex min-w-0 flex-1 flex-col gap-1 text-sm text-muted">
            {t("profile.avatarUrl")}
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
              // s'afficher, sans rien dire : la politique de sécurité de
              // contenu n'autorise que les images de ce site. Un champ qui
              // ment est pire qu'un champ qui refuse.
              <span className="text-xs text-danger">{t("profile.avatarBlocked")}</span>
            )}
          </label>
        </div>
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
