"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { inputClass, primaryButtonClass } from "@/components/AuthCard";
import KeyRotationSettings from "@/components/KeyRotationSettings";
import {
  deleteAccount,
  downloadExport,
  getRetention,
  setRetention,
} from "@/lib/account";
import { ApiError } from "@/lib/api";
import { getMe, logout } from "@/lib/auth";
import { useT } from "@/lib/i18n";
import { getActiveOrg } from "@/lib/auth";
import { getMyOrganizations } from "@/lib/organization";

const MANAGER_ROLES = ["owner", "admin"];
// Mirrors the application service and the database check constraint (ADR-0006).
const MIN_RETENTION_DAYS = 30;

export default function PrivacySettings() {
  const t = useT();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [canManage, setCanManage] = useState(false);
  const [hasPassword, setHasPassword] = useState(true);

  const [retention, setRetentionState] = useState<number | null>(null);
  const [retentionInput, setRetentionInput] = useState("");
  const [retentionSaved, setRetentionSaved] = useState(false);

  const [exporting, setExporting] = useState(false);
  const [exportNote, setExportNote] = useState<string | null>(null);

  const [confirmEmail, setConfirmEmail] = useState("");
  const [password, setPassword] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [armed, setArmed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([getMe(), getMyOrganizations()])
      .then(async ([me, orgs]) => {
        if (!active) return;
        setEmail(me.email);
        // An SSO-only account has no password to confirm with; the typed address is its only gate.
        setHasPassword(me.has_password ?? true);
        const current = orgs.find((o) => o.id === getActiveOrg()) ?? orgs[0];
        const manager =
          current !== undefined && MANAGER_ROLES.includes(current.role);
        setCanManage(manager);
        if (manager) {
          const window = await getRetention();
          if (!active) return;
          setRetentionState(window.booking_retention_days);
          setRetentionInput(window.booking_retention_days?.toString() ?? "");
        }
      })
      .catch(() => active && setError(t("common.errGeneric")));
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function runExport() {
    setExporting(true);
    setExportNote(null);
    setError(null);
    try {
      const unopened = await downloadExport();
      setExportNote(
        unopened > 0
          ? t("privacy.exportPartial").replace("{n}", String(unopened))
          : t("privacy.exportDone"),
      );
    } catch {
      setError(t("privacy.errExport"));
    } finally {
      setExporting(false);
    }
  }

  async function saveRetention(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setRetentionSaved(false);
    const trimmed = retentionInput.trim();
    const days = trimmed === "" ? null : Number(trimmed);
    if (
      days !== null &&
      (!Number.isInteger(days) || days < MIN_RETENTION_DAYS)
    ) {
      setError(
        t("privacy.errRetentionFloor").replace(
          "{n}",
          String(MIN_RETENTION_DAYS),
        ),
      );
      return;
    }
    try {
      const saved = await setRetention(days);
      setRetentionState(saved.booking_retention_days);
      setRetentionSaved(true);
    } catch {
      setError(t("privacy.errRetention"));
    }
  }

  async function confirmDelete(e: React.FormEvent) {
    e.preventDefault();
    setDeleting(true);
    setError(null);
    try {
      await deleteAccount(confirmEmail, hasPassword ? password : null);
      await logout();
      router.replace("/");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError(t("privacy.errSoleOwner"));
      } else if (err instanceof ApiError && err.status === 403) {
        setError(t("privacy.errPassword"));
      } else if (err instanceof ApiError && err.status === 400) {
        setError(t("privacy.errConfirm"));
      } else {
        setError(t("common.errGeneric"));
      }
      setDeleting(false);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <section>
        <h2 className="text-lg font-semibold text-foreground">
          {t("privacy.exportTitle")}
        </h2>
        <p className="mt-1 text-sm text-muted">{t("privacy.exportSub")}</p>
        <button
          type="button"
          onClick={runExport}
          disabled={exporting}
          className={`${primaryButtonClass} mt-4`}
        >
          {exporting ? t("privacy.exporting") : t("privacy.export")}
        </button>
        {exportNote && <p className="mt-2 text-sm text-accent">{exportNote}</p>}
      </section>

      {canManage && (
        <section className="border-t border-border pt-6">
          <h2 className="text-lg font-semibold text-foreground">
            {t("privacy.retentionTitle")}
          </h2>
          <p className="mt-1 text-sm text-muted">{t("privacy.retentionSub")}</p>
          <form
            onSubmit={saveRetention}
            className="mt-4 flex flex-wrap items-end gap-3"
          >
            <label className="flex flex-col gap-1 text-sm text-muted">
              {t("privacy.retentionDays")}
              <input
                value={retentionInput}
                onChange={(e) => {
                  setRetentionSaved(false);
                  setRetentionInput(e.target.value);
                }}
                inputMode="numeric"
                placeholder={t("privacy.retentionForever")}
                className={`${inputClass} w-40`}
              />
            </label>
            <button type="submit" className={primaryButtonClass}>
              {t("common.save")}
            </button>
            {retentionSaved && (
              <span className="text-sm text-accent">
                {retention === null
                  ? t("privacy.retentionCleared")
                  : t("common.saved")}
              </span>
            )}
          </form>
          <p className="mt-2 text-xs text-muted">
            {t("privacy.retentionHint")}
          </p>
        </section>
      )}

      {canManage && <KeyRotationSettings />}

      <section className="rounded-xl border border-red-500/40 bg-red-500/5 p-5">
        <h2 className="text-lg font-semibold text-red-400">
          {t("privacy.deleteTitle")}
        </h2>
        <p className="mt-1 text-sm text-muted">{t("privacy.deleteSub")}</p>

        {!armed ? (
          <button
            type="button"
            onClick={() => setArmed(true)}
            className="mt-4 rounded-lg border border-red-500/60 px-4 py-2 text-sm font-medium text-red-400 transition hover:bg-red-500/10"
          >
            {t("privacy.delete")}
          </button>
        ) : (
          <form onSubmit={confirmDelete} className="mt-4 flex flex-col gap-4">
            <label className="flex flex-col gap-1 text-sm text-muted">
              {t("privacy.typeEmail").replace("{email}", email)}
              <input
                value={confirmEmail}
                onChange={(e) => setConfirmEmail(e.target.value)}
                autoComplete="off"
                className={inputClass}
              />
            </label>
            {hasPassword && (
              <label className="flex flex-col gap-1 text-sm text-muted">
                {t("common.password")}
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  className={inputClass}
                />
              </label>
            )}
            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={
                  deleting ||
                  confirmEmail.trim().toLowerCase() !== email.toLowerCase()
                }
                className="rounded-lg bg-red-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-600 disabled:opacity-40"
              >
                {deleting ? t("privacy.deleting") : t("privacy.deleteConfirm")}
              </button>
              <button
                type="button"
                onClick={() => setArmed(false)}
                className="text-sm text-muted hover:text-foreground"
              >
                {t("common.cancel")}
              </button>
            </div>
          </form>
        )}
      </section>

      {error && <p className="text-sm text-red-400">{error}</p>}
    </div>
  );
}
