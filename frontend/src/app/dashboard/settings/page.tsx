"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { inputClass, primaryButtonClass } from "@/components/AuthCard";
import CalendarSettings from "@/components/CalendarSettings";
import PrivacySettings from "@/components/PrivacySettings";
import WebhookSettings from "@/components/WebhookSettings";
import { ApiError } from "@/lib/api";
import { isAuthenticated } from "@/lib/auth";
import { useT } from "@/lib/i18n";
import { getOrganization, updateOrganization } from "@/lib/organization";

export default function SettingsPage() {
  const t = useT();
  const router = useRouter();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<"idle" | "saved" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/login");
      return;
    }
    getOrganization()
      .then((o) => {
        setName(o.name);
        setSlug(o.slug);
      })
      .catch(() => router.replace("/login"))
      .finally(() => setLoading(false));
  }, [router]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setStatus("idle");
    try {
      const updated = await updateOrganization({ name, slug });
      setName(updated.name);
      setSlug(updated.slug);
      setStatus("saved");
    } catch (err) {
      setStatus("error");
      if (err instanceof ApiError && err.status === 409) {
        setError(t("settings.errTaken"));
      } else if (err instanceof ApiError && err.status === 422) {
        setError(t("settings.errInvalid"));
      } else {
        setError(t("settings.errGeneric"));
      }
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <main className="flex flex-1 items-center justify-center p-8">
        <p className="text-sm text-muted">{t("common.loading")}</p>
      </main>
    );
  }

  const origin = typeof window !== "undefined" ? window.location.origin : "";

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-6 p-6 sm:p-10">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">
          {t("settings.title")}
        </h1>
        <p className="mt-1 text-sm text-muted">{t("settings.sub")}</p>
      </div>

      <form
        onSubmit={save}
        className="glass flex flex-col gap-5 rounded-2xl p-6 sm:p-8"
      >
        <label className="flex flex-col gap-1 text-sm text-muted">
          {t("settings.orgName")}
          <input
            value={name}
            onChange={(e) => {
              setStatus("idle");
              setName(e.target.value);
            }}
            className={inputClass}
          />
        </label>

        <label className="flex flex-col gap-1 text-sm text-muted">
          {t("settings.handle")}
          <input
            value={slug}
            onChange={(e) => {
              setStatus("idle");
              setSlug(e.target.value.toLowerCase());
            }}
            className={inputClass}
            placeholder="kevin"
          />
        </label>

        <p className="rounded-lg border border-border bg-surface-2/50 px-4 py-3 text-sm text-muted">
          {t("settings.yourBookingPage")}{" "}
          <span className="text-accent">
            {origin}/{slug || "your-handle"}
          </span>
        </p>

        {error && <p className="text-sm text-red-400">{error}</p>}
        <div className="flex items-center gap-4">
          <button
            type="submit"
            disabled={saving}
            className={primaryButtonClass}
          >
            {saving ? t("common.saving") : t("common.save")}
          </button>
          {status === "saved" && (
            <span className="text-sm text-accent">{t("common.saved")}</span>
          )}
        </div>
      </form>

      <section className="glass rounded-2xl p-6 sm:p-8">
        <CalendarSettings />
      </section>

      <section className="glass rounded-2xl p-6 sm:p-8">
        <WebhookSettings />
      </section>

      <section className="glass rounded-2xl p-6 sm:p-8">
        <div className="mb-6">
          <h2 className="text-lg font-semibold text-foreground">
            {t("privacy.title")}
          </h2>
          <p className="mt-1 text-sm text-muted">{t("privacy.sub")}</p>
        </div>
        <PrivacySettings />
      </section>
    </main>
  );
}
