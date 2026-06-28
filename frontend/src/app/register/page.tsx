"use client";

import Link from "next/link";
import { useState } from "react";
import AuthCard, { inputClass, primaryButtonClass } from "@/components/AuthCard";
import { ApiError } from "@/lib/api";
import { register } from "@/lib/auth";
import { useT } from "@/lib/i18n";

export default function RegisterPage() {
  const t = useT();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await register(email, name, password);
      setDone(true);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? t("register.errTaken")
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
          <Link href="/login" className="text-accent hover:underline">
            {t("register.backToSignIn")}
          </Link>
        }
      >
        <p className="text-sm text-muted">{t("register.expires")}</p>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title={t("register.title")}
      footer={
        <>
          {t("register.haveAccount")}{" "}
          <Link href="/login" className="text-accent hover:underline">
            {t("common.signIn")}
          </Link>
        </>
      }
    >
      <form className="flex flex-col gap-3" onSubmit={onSubmit}>
        <input
          required
          placeholder={t("register.yourName")}
          value={name}
          onChange={(e) => setName(e.target.value)}
          className={inputClass}
        />
        <input
          required
          type="email"
          placeholder={t("common.email")}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className={inputClass}
        />
        <input
          required
          type="password"
          minLength={8}
          placeholder={t("register.passwordPh")}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={inputClass}
        />
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button type="submit" disabled={submitting} className={primaryButtonClass}>
          {submitting ? t("register.submitting") : t("register.submit")}
        </button>
      </form>
    </AuthCard>
  );
}
