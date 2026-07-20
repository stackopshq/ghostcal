"use client";

import { useEffect, useMemo, useState } from "react";
import { inputClass, primaryButtonClass } from "@/components/AuthCard";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { changePassword, getProfile, updateProfile } from "@/lib/profile";
import { MIN_PASSWORD_LENGTH } from "@/lib/passwords";

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
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={avatar || "https://api.dicebear.com/9.x/initials/svg?seed=" + name}
            alt=""
            className="h-14 w-14 rounded-full border border-border-strong object-cover"
          />
          <label className="flex flex-1 flex-col gap-1 text-sm text-muted">
            {t("profile.avatarUrl")}
            <input
              type="url"
              placeholder="https://…/avatar.png"
              value={avatar}
              onChange={(e) => setAvatar(e.target.value)}
              className={inputClass}
            />
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
