"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import AuthCard, { inputClass, primaryButtonClass } from "@/components/AuthCard";
import { useT } from "@/lib/i18n";
import {
  outlookFor,
  type ResetBundle,
  resetWithRecoveryPhrase,
  zkKeysForReset,
} from "@/lib/recovery";

/**
 * Finish a reset with the recovery phrase.
 *
 * The screen says what it can and cannot reopen **before** the user commits. A reset that quietly
 * restores part of a calendar is worse than one that refuses: the missing part is indistinguishable
 * from deleted data, and the user has no way to learn otherwise.
 *
 * Two degraded cases, and they are different:
 *  - some generations have no recovery envelope — they were sealed to the user keypair, which has
 *    none. The reset works, and those stay shut. Say how many.
 *  - none of them do. The phrase cannot reopen anything here, and offering the form would be a lie.
 */
export default function ResetPasswordPage() {
  const t = useT();
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [bundles, setBundles] = useState<ResetBundle[] | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "bad-link">(
    "loading",
  );
  const [phrase, setPhrase] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const raw = new URLSearchParams(window.location.search).get("token");
    if (!raw) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setState("bad-link");
      return;
    }
    setToken(raw);
    zkKeysForReset(raw)
      .then((b) => {
        setBundles(b);
        setState("ready");
      })
      .catch(() => setState("bad-link"));
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token || !bundles) return;
    setError(null);
    setSubmitting(true);
    try {
      await resetWithRecoveryPhrase(token, bundles, phrase, password);
      router.replace("/login?reason=password-reset");
    } catch {
      // A wrong phrase fails here, on AES-GCM authentication, before anything is sent. The link is
      // not spent — reading the envelopes does not consume it — so this is retryable.
      setError(t("reset.wrongPhrase"));
      setSubmitting(false);
    }
  }

  if (state === "loading") {
    return (
      <AuthCard title={t("reset.title")}>
        <p className="text-sm text-muted">{t("common.loading")}</p>
      </AuthCard>
    );
  }

  if (state === "bad-link" || !bundles) {
    return (
      <AuthCard
        title={t("reset.badLinkTitle")}
        footer={
          <Link href="/forgot-password" className="text-accent hover:underline">
            {t("reset.askAgain")}
          </Link>
        }
      >
        <p className="text-sm text-muted">{t("reset.badLinkBody")}</p>
      </AuthCard>
    );
  }

  const { recoverable, lost } = outlookFor(bundles);

  if (recoverable.length === 0) {
    return (
      <AuthCard
        title={t("reset.title")}
        footer={
          <Link href="/login" className="text-accent hover:underline">
            {t("forgot.backToLogin")}
          </Link>
        }
      >
        <p className="text-sm text-muted">{t("reset.nothingRecoverable")}</p>
      </AuthCard>
    );
  }

  return (
    <AuthCard title={t("reset.title")} subtitle={t("reset.subtitle")}>
      <form className="flex flex-col gap-3" onSubmit={onSubmit}>
        <input
          required
          autoComplete="off"
          placeholder={t("reset.phrasePlaceholder")}
          value={phrase}
          onChange={(e) => setPhrase(e.target.value)}
          className={inputClass}
        />
        <input
          required
          type="password"
          autoComplete="new-password"
          placeholder={t("reset.newPassword")}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={inputClass}
        />
        {lost.length > 0 && (
          <p className="text-2xs text-muted">
            {t("reset.partialWarning").replace("{n}", String(lost.length))}
          </p>
        )}
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button
          type="submit"
          disabled={submitting}
          className={primaryButtonClass}
        >
          {submitting ? t("common.saving") : t("reset.submit")}
        </button>
      </form>
    </AuthCard>
  );
}
