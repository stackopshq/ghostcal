"use client";

import { useEffect, useMemo, useState } from "react";
import { inputClass, primaryButtonClass } from "@/components/AuthCard";
import { ApiError } from "@/lib/api";
import { changePassword, getProfile, updateProfile } from "@/lib/profile";

function timezones(fallback: string): string[] {
  const fn = (Intl as { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf;
  try {
    return fn ? fn("timeZone") : [fallback];
  } catch {
    return [fallback];
  }
}

export default function ProfileSettings() {
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
      .catch(() => active && setProfileError("Could not load your profile."));
    return () => {
      active = false;
    };
  }, []);

  async function saveProfile(e: React.FormEvent) {
    e.preventDefault();
    setProfileError(null);
    setSavedProfile(false);
    try {
      await updateProfile({ name, timezone: tz, avatar_url: avatar.trim() || null });
      setSavedProfile(true);
    } catch {
      setProfileError("Could not save your profile (check the avatar URL).");
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
          ? "Current password is incorrect."
          : "Could not change your password (min 8 characters).",
      );
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <h2 className="text-lg font-semibold text-foreground">Your profile</h2>

      <form onSubmit={saveProfile} className="flex flex-col gap-4">
        <div className="flex items-center gap-4">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={avatar || "https://api.dicebear.com/9.x/initials/svg?seed=" + name}
            alt=""
            className="h-14 w-14 rounded-full border border-border-strong object-cover"
          />
          <label className="flex flex-1 flex-col gap-1 text-sm text-muted">
            Avatar URL
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
          Email
          <input value={email} disabled className={`${inputClass} opacity-60`} />
        </label>
        <label className="flex flex-col gap-1 text-sm text-muted">
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} className={inputClass} />
        </label>
        <label className="flex flex-col gap-1 text-sm text-muted">
          Time zone
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
            Save profile
          </button>
          {savedProfile && <span className="text-sm text-accent">Saved ✓</span>}
        </div>
      </form>

      <form onSubmit={savePassword} className="flex flex-col gap-4 border-t border-border pt-6">
        <h3 className="text-sm font-medium text-foreground">Change password</h3>
        <input
          type="password"
          required
          placeholder="Current password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          className={inputClass}
        />
        <input
          type="password"
          required
          minLength={8}
          placeholder="New password (min 8 characters)"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          className={inputClass}
        />
        {passwordError && <p className="text-sm text-red-400">{passwordError}</p>}
        <div className="flex items-center gap-4">
          <button type="submit" className={primaryButtonClass}>
            Update password
          </button>
          {savedPassword && <span className="text-sm text-accent">Updated ✓</span>}
        </div>
      </form>
    </div>
  );
}
