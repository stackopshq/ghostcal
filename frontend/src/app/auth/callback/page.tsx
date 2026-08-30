"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import AuthCard, { inputClass, primaryButtonClass } from "@/components/AuthCard";
import {
  completeOidcSession,
  hasZkKeys,
  setupEncryptionPassphrase,
  unlockZkKeys,
} from "@/lib/auth";
import { useT } from "@/lib/i18n";
import { MIN_PASSWORD_LENGTH } from "@/lib/passwords";

// Where an SSO round-trip lands. The session tokens arrive in the URL fragment; we then either
// unlock the zero-knowledge vault with the user's encryption passphrase, or — on first SSO login —
// have them choose one. SSO proves *who* you are; this passphrase (never sent to the server) is
// what decrypts your content.
type Phase = "loading" | "unlock" | "setup" | "recovery";

export default function OidcCallbackPage() {
  const t = useT();
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("loading");
  const [passphrase, setPassphrase] = useState("");
  const [confirm, setConfirm] = useState("");
  const [recoveryPhrase, setRecoveryPhrase] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!completeOidcSession()) {
      router.replace("/login");
      return;
    }
    hasZkKeys()
      .then((has) => setPhase(has ? "unlock" : "setup"))
      .catch(() => router.replace("/login?sso_error=1"));
  }, [router]);

  async function onUnlock(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { unlocked } = await unlockZkKeys(passphrase);
      if (unlocked > 0) router.replace("/dashboard");
      else setError(t("callback.errWrong"));
    } catch {
      setError(t("callback.errWrong"));
    } finally {
      setBusy(false);
    }
  }

  async function onSetup(e: React.FormEvent) {
    e.preventDefault();
    if (passphrase !== confirm) {
      setError(t("callback.errMismatch"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setRecoveryPhrase(await setupEncryptionPassphrase(passphrase));
      setPhase("recovery");
    } catch {
      setError(t("callback.errGeneric"));
    } finally {
      setBusy(false);
    }
  }

  if (phase === "loading") {
    return (
      <AuthCard title={t("callback.signingIn")}>
        <p className="text-sm text-muted">{t("common.loading")}</p>
      </AuthCard>
    );
  }

  if (phase === "recovery") {
    return (
      <AuthCard title={t("callback.recoveryTitle")} subtitle={t("callback.recoverySub")}>
        <div className="flex flex-col gap-4">
          <div className="rounded-md border border-accent/40 bg-surface-2/60 p-4">
            <p className="mb-2 flex items-center gap-1.5 text-sm font-medium text-accent">
              <span aria-hidden>🔑</span> {t("register.recoveryTitle")}
            </p>
            <code className="block break-all rounded-lg bg-base/80 px-3 py-2 font-mono text-sm text-foreground">
              {recoveryPhrase}
            </code>
            <button
              type="button"
              onClick={() => void navigator.clipboard?.writeText(recoveryPhrase)}
              className="mt-2 text-xs text-accent hover:underline"
            >
              {t("register.recoveryCopy")}
            </button>
          </div>
          <button
            type="button"
            onClick={() => router.replace("/dashboard")}
            className={primaryButtonClass}
          >
            {t("callback.continue")}
          </button>
        </div>
      </AuthCard>
    );
  }

  const isSetup = phase === "setup";
  return (
    <AuthCard
      title={isSetup ? t("callback.setupTitle") : t("callback.unlockTitle")}
      subtitle={isSetup ? t("callback.setupSub") : t("callback.unlockSub")}
    >
      <form className="flex flex-col gap-3" onSubmit={isSetup ? onSetup : onUnlock}>
        <input
          required
          autoFocus
          type="password"
          minLength={MIN_PASSWORD_LENGTH}
          placeholder={t("callback.passphrasePh")}
          value={passphrase}
          onChange={(e) => setPassphrase(e.target.value)}
          className={inputClass}
        />
        {isSetup && (
          <input
            required
            type="password"
            minLength={MIN_PASSWORD_LENGTH}
            placeholder={t("callback.confirmPh")}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className={inputClass}
          />
        )}
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button type="submit" disabled={busy} className={primaryButtonClass}>
          {busy
            ? t("common.loading")
            : isSetup
              ? t("callback.setupSubmit")
              : t("callback.unlockSubmit")}
        </button>
      </form>
    </AuthCard>
  );
}
