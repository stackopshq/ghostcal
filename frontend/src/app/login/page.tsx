"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import AuthCard, { inputClass, primaryButtonClass } from "@/components/AuthCard";
import { ApiError } from "@/lib/api";
import { login } from "@/lib/auth";
import { useT } from "@/lib/i18n";

// Where to land after login: honour a ?next= destination if it's a safe internal path, else the
// dashboard. Only same-origin relative paths are allowed — reject protocol-relative or absolute
// URLs so ?next= can't be turned into an open redirect.
function safeNext(): string {
  if (typeof window === "undefined") return "/dashboard";
  const raw = new URLSearchParams(window.location.search).get("next");
  if (raw && raw.startsWith("/") && !raw.startsWith("//") && !raw.startsWith("/\\")) return raw;
  return "/dashboard";
}

export default function LoginPage() {
  const t = useT();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email, password);
      router.push(safeNext());
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError(t("login.errVerify"));
      } else if (err instanceof ApiError && err.status === 401) {
        setError(t("login.errInvalid"));
      } else {
        setError(t("common.errGeneric"));
      }
      setSubmitting(false);
    }
  }

  return (
    <AuthCard
      title={t("login.title")}
      footer={
        <>
          {t("login.newHere")}{" "}
          <Link href="/register" className="text-accent hover:underline">
            {t("login.create")}
          </Link>
        </>
      }
    >
      <form className="flex flex-col gap-3" onSubmit={onSubmit}>
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
          placeholder={t("common.password")}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={inputClass}
        />
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button type="submit" disabled={submitting} className={primaryButtonClass}>
          {submitting ? t("login.submitting") : t("login.title")}
        </button>
      </form>
    </AuthCard>
  );
}
