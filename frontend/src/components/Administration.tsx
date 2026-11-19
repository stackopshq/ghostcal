"use client";

// The instance administration view: sign-up open or closed, and every account.
//
// Shown to the addresses in GHOSTCAL_ADMIN_EMAILS. The server answers 404 to anyone else, and
// this component treats a 404 the same way: as a page that does not exist.

import { useCallback, useEffect, useState } from "react";
import { Champ, inputClass, primaryButtonClass } from "@/components/AuthCard";
import {
  actionsFor,
  confirmationMatches,
  deleteAccount,
  getRegistration,
  listAccounts,
  needsConfirmation,
  reactivateAccount,
  setRegistration,
  suspendAccount,
  type AdminAccount,
  type RegistrationState,
} from "@/lib/administration";
import { ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const quietButton =
  "rounded-pill border border-border-strong px-3 py-1.5 text-xs font-medium text-foreground transition hover:border-accent hover:text-accent disabled:opacity-60";
const dangerButton =
  "rounded-pill border border-red-400/50 px-3 py-1.5 text-xs font-medium text-red-400 transition hover:bg-red-400/10 disabled:opacity-60";
const badge = "rounded-pill px-2 py-0.5 text-2xs font-medium";

export default function Administration({ onNotFound }: { onNotFound: () => void }) {
  const { t, locale } = useI18n();
  const [registration, setRegistrationState] = useState<RegistrationState | null>(null);
  const [accounts, setAccounts] = useState<AdminAccount[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // The account whose erasure is being confirmed, and what has been typed so far.
  const [erasing, setErasing] = useState<AdminAccount | null>(null);
  const [typed, setTyped] = useState("");

  const load = useCallback(async () => {
    const [reg, list] = await Promise.all([getRegistration(), listAccounts()]);
    return { reg, list };
  }, []);

  useEffect(() => {
    load()
      .then(({ reg, list }) => {
        setRegistrationState(reg);
        setAccounts(list);
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 404) onNotFound();
        else setError(t("common.errGeneric"));
      });
  }, [load, onNotFound, t]);

  async function reload() {
    const { reg, list } = await load();
    setRegistrationState(reg);
    setAccounts(list);
  }

  function explain(err: unknown) {
    if (!(err instanceof ApiError)) return setError(t("common.errGeneric"));
    switch (err.code) {
      case "account_is_admin":
        return setError(t("admin.errIsAdmin"));
      case "registration_fixed":
        return setError(t("admin.errFixed"));
      case "sole_owner":
        return setError(t("admin.errSoleOwner"));
      case "confirmation_mismatch":
        return setError(t("admin.errMismatch"));
      default:
        return setError(t("common.errGeneric"));
    }
  }

  async function act(what: () => Promise<void>) {
    setError(null);
    setBusy(true);
    try {
      await what();
      await reload();
    } catch (err) {
      explain(err);
    } finally {
      setBusy(false);
    }
  }

  function toggleRegistration() {
    if (!registration) return;
    const open = !registration.open;
    if (needsConfirmation(open) && !confirm(t("admin.confirmOpen"))) return;
    void act(async () => {
      setRegistrationState(await setRegistration(open));
    });
  }

  const date = (iso: string | null) =>
    iso
      ? new Date(iso).toLocaleDateString(locale, { year: "numeric", month: "short", day: "numeric" })
      : t("admin.never");

  if (!registration || !accounts) {
    return error ? (
      <p className="text-sm text-red-400">{error}</p>
    ) : (
      <p className="text-sm text-muted">{t("common.loading")}</p>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <section className="glass rounded-lg p-6 sm:p-8">
        <h2 className="text-lg font-semibold text-foreground">{t("admin.registration")}</h2>
        <p className="mt-1 text-sm text-muted">
          {registration.open ? t("admin.registrationOpen") : t("admin.registrationClosed")}
        </p>
        {registration.fixed ? (
          <p className="mt-3 rounded-lg border border-border bg-surface-2/50 px-4 py-3 text-sm text-muted">
            {t("admin.registrationFixed")}
          </p>
        ) : (
          <button
            type="button"
            disabled={busy}
            onClick={toggleRegistration}
            className={`mt-4 ${primaryButtonClass}`}
          >
            {registration.open ? t("admin.close") : t("admin.open")}
          </button>
        )}
      </section>

      <section className="glass rounded-lg p-6 sm:p-8">
        <h2 className="text-lg font-semibold text-foreground">
          {t("admin.accounts", { n: accounts.length })}
        </h2>
        <p className="mt-1 text-sm text-muted">{t("admin.accountsSub")}</p>

        <ul className="mt-4 divide-y divide-border">
          {accounts.map((a) => (
            <li key={a.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center">
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-foreground">
                  <span className="truncate">{a.email}</span>
                  {a.is_admin && (
                    <span className={`${badge} bg-accent/15 text-accent`}>{t("admin.badgeAdmin")}</span>
                  )}
                  {a.suspended_at && (
                    <span className={`${badge} bg-red-400/15 text-red-400`}>
                      {t("admin.badgeSuspended")}
                    </span>
                  )}
                  {!a.email_verified && (
                    <span className={`${badge} bg-surface-2 text-muted`}>{t("admin.badgeUnverified")}</span>
                  )}
                </p>
                <p className="mt-0.5 text-xs text-muted">
                  {t("admin.created", { date: date(a.created_at) })} ·{" "}
                  {t("admin.lastLogin", { date: date(a.last_login_at) })} ·{" "}
                  {a.two_factor_enabled ? t("admin.mfaOn") : t("admin.mfaOff")}
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                {actionsFor(a).map((action) =>
                  action === "delete" ? (
                    <button
                      key={action}
                      type="button"
                      disabled={busy}
                      className={dangerButton}
                      onClick={() => {
                        setError(null);
                        setTyped("");
                        setErasing(a);
                      }}
                    >
                      {t("admin.delete")}
                    </button>
                  ) : (
                    <button
                      key={action}
                      type="button"
                      disabled={busy}
                      className={quietButton}
                      onClick={() =>
                        void act(() =>
                          action === "suspend" ? suspendAccount(a.id) : reactivateAccount(a.id),
                        )
                      }
                    >
                      {action === "suspend" ? t("admin.suspend") : t("admin.reactivate")}
                    </button>
                  ),
                )}
              </div>
            </li>
          ))}
        </ul>
      </section>

      {erasing && (
        <section className="glass rounded-lg border border-red-400/40 p-6 sm:p-8">
          <h2 className="text-lg font-semibold text-foreground">{t("admin.deleteTitle")}</h2>
          <p className="mt-1 text-sm text-muted">{t("admin.deleteSub", { email: erasing.email })}</p>
          <form
            className="mt-4 flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              const target = erasing;
              void act(async () => {
                await deleteAccount(target.id, typed);
                setErasing(null);
                setTyped("");
              });
            }}
          >
            <Champ label={t("admin.deleteType")}>
              <input
                autoFocus
                autoComplete="off"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                className={inputClass}
                placeholder={erasing.email}
              />
            </Champ>
            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={busy || !confirmationMatches(erasing, typed)}
                className={dangerButton}
              >
                {t("admin.deleteConfirm")}
              </button>
              <button type="button" className={quietButton} onClick={() => setErasing(null)}>
                {t("common.cancel")}
              </button>
            </div>
          </form>
        </section>
      )}

      {error && <p className="text-sm text-red-400">{error}</p>}
    </div>
  );
}
