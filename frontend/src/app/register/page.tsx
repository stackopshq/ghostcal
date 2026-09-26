"use client";

import Link from "next/link";
import { useState } from "react";
import AuthCard, { Champ, inputClass, lienDePied, primaryButtonClass } from "@/components/AuthCard";
import { ApiError } from "@/lib/api";
import { register } from "@/lib/auth";
import { useT } from "@/lib/i18n";
import { MIN_PASSWORD_LENGTH } from "@/lib/passwords";
import {
  KeyIcon,
} from "@/components/icons";

export default function RegisterPage() {
  const t = useT();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const [recoveryPhrase, setRecoveryPhrase] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const { recovery_phrase } = await register(email, name, password);
      setRecoveryPhrase(recovery_phrase);
      setDone(true);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? t("register.errTaken")
          : // 422 carries the password-policy reason (too short, or found in a breach corpus).
            // Showing it verbatim beats a generic failure the user cannot act on.
            err instanceof ApiError && err.status === 422
            ? err.detail || t("register.errGeneric")
            : t("register.errGeneric"),
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (done) {
    return (
      <AuthCard
        title={t("register.checkInbox")}
        subtitle={t("register.checkInboxSub", { email })}
        footer={
          <Link href="/login" className={lienDePied}>
            {t("register.backToSignIn")}
          </Link>
        }
      >
        <div className="flex flex-col gap-4">
          <div className="rounded border border-accent/40 bg-surface-2/60 p-4">
            <p className="mb-2 flex items-center gap-1.5 text-sm font-medium text-accent">
              <KeyIcon /> {t("register.recoveryTitle")}
            </p>
            <p className="mb-3 text-xs text-muted">{t("register.recoverySub")}</p>
            <code className="block break-all rounded-lg bg-base/80 px-3 py-2 font-mono text-sm text-foreground">
              {recoveryPhrase}
            </code>
            <button
              type="button"
              onClick={() => void navigator.clipboard?.writeText(recoveryPhrase)}
              className={`mt-2 text-xs ${lienDePied}`}
            >
              {t("register.recoveryCopy")}
            </button>
          </div>
          <p className="text-sm text-muted">{t("register.expires")}</p>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title={t("register.title")}
      footer={
        <>
          {t("register.haveAccount")}{" "}
          <Link href="/login" className={lienDePied}>
            {t("common.signIn")}
          </Link>
        </>
      }
    >
      <form className="flex flex-col gap-3" onSubmit={onSubmit}>
        <Champ label={t("register.yourName")}>
          <input
            required
            autoComplete="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={inputClass}
          />
        </Champ>
        <Champ label={t("common.email")}>
          <input
            required
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={inputClass}
          />
        </Champ>
        {/* L'exigence vient de `MIN_PASSWORD_LENGTH`, la seule source. La phrase
            annonçait « 8 caractères min. » pendant que `minLength` en imposait 12 :
            un mot de passe de 9 caractères satisfaisait l'étiquette et se faisait
            refuser par le navigateur, sans que rien n'explique l'écart. */}
        <Champ label={t("register.password")}>
          <input
            required
            type="password"
            minLength={MIN_PASSWORD_LENGTH}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={inputClass}
          />
          <span className="text-xs text-muted">
            {t("register.passwordHint", { min: MIN_PASSWORD_LENGTH })}
          </span>
        </Champ>
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button type="submit" disabled={submitting} className={primaryButtonClass}>
          {submitting ? t("register.submitting") : t("register.submit")}
        </button>
      </form>
    </AuthCard>
  );
}
