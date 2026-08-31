"use client";

import { useState } from "react";
import { unlockZkKeys } from "@/lib/auth";
import { useT } from "@/lib/i18n";

/**
 * The locked banner, with the one thing it was missing: a way out.
 *
 * The calendar and the task list both render "Locked. Sign in again to unlock your calendar in this
 * browser." — and offered no control at all. Worse, the instruction was wrong: `unlockZkKeys` was
 * only ever called from `/auth/callback`, a page reachable solely at the end of an SSO round-trip.
 * So a user who lost the per-tab key had to sign out and back in, guess that, and find the sign-out
 * button inside a drawer they could not see was there.
 *
 * Nothing about the situation actually requires a new session: the wrapped private key is on the
 * server and the passphrase unwraps it. This asks for the passphrase where the lock is shown.
 *
 * On success the page is reloaded rather than the parent being told. The keys land in per-tab
 * session storage and are read at mount by several independent components — a reload is how they
 * all see the new state, and it is honest about that rather than threading a callback through two
 * thousand-line pages and hoping every reader re-runs.
 */
export default function UnlockBanner() {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [passphrase, setPassphrase] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { unlocked } = await unlockZkKeys(passphrase);
      if (unlocked > 0) window.location.reload();
      else setError(t("callback.errWrong"));
    } catch {
      setError(t("callback.errWrong"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="glass rounded border-l-[3px] border-l-accent p-3 text-sm text-accent/90">
      <div className="flex flex-wrap items-center gap-2">
        <span aria-hidden>🔒</span>
        <span className="min-w-0 flex-1">{t("calendar.locked")}</span>
        {!open && (
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="shrink-0 rounded-pill bg-accent px-3 py-1.5 text-sm font-semibold text-accent-ink transition hover:brightness-110"
          >
            {t("callback.unlockSubmit")}
          </button>
        )}
      </div>

      {open && (
        <form onSubmit={onSubmit} className="mt-3 flex flex-wrap items-center gap-2">
          <input
            type="password"
            autoFocus
            autoComplete="current-password"
            value={passphrase}
            onChange={(e) => setPassphrase(e.target.value)}
            placeholder={t("callback.unlockTitle")}
            className="min-w-0 flex-1 rounded border border-border bg-surface-2/40 px-3 py-2 text-sm text-foreground outline-none focus:border-accent"
          />
          <button
            type="submit"
            disabled={busy || !passphrase}
            className="shrink-0 rounded-pill bg-accent px-3 py-2 text-sm font-semibold text-accent-ink transition hover:brightness-110 disabled:opacity-40"
          >
            {busy ? t("common.saving") : t("callback.unlockSubmit")}
          </button>
          {error && <p className="w-full text-xs text-danger">{error}</p>}
        </form>
      )}
    </div>
  );
}
