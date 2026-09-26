"use client";

import Link from "next/link";
import { useState } from "react";

import AuthCard, { Champ, inputClass, lienDePied, primaryButtonClass } from "@/components/AuthCard";
import { useT } from "@/lib/i18n";
import { requestPasswordReset } from "@/lib/recovery";

/**
 * Ask for a reset link.
 *
 * The answer is the same whether the address is known or not — the server returns 202 either way,
 * and so does this screen. Saying "no such account" here would tell anyone who asks which addresses
 * have one.
 */
export default function ForgotPasswordPage() {
  const t = useT();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await requestPasswordReset(email);
    } finally {
      // Shown even if the request failed: a network error must not become a signal about the
      // address either.
      setSent(true);
      setSubmitting(false);
    }
  }

  return (
    <AuthCard
      title={t("forgot.title")}
      subtitle={t("forgot.subtitle")}
      footer={
        <Link href="/login" className={lienDePied}>
          {t("forgot.backToLogin")}
        </Link>
      }
    >
      {sent ? (
        <p className="text-sm text-muted">{t("forgot.sent")}</p>
      ) : (
        <form className="flex flex-col gap-3" onSubmit={onSubmit}>
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
          <button
            type="submit"
            disabled={submitting}
            className={primaryButtonClass}
          >
            {submitting ? t("common.saving") : t("forgot.send")}
          </button>
          <p className="text-2xs text-muted">{t("forgot.phraseWarning")}</p>
        </form>
      )}
    </AuthCard>
  );
}
