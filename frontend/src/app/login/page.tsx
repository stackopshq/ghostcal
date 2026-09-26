"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import AuthCard, { Champ, inputClass, lienDePied, primaryButtonClass } from "@/components/AuthCard";
import { ApiError } from "@/lib/api";
import { beginOidcLogin, getAuthConfig, login } from "@/lib/auth";
import { useT } from "@/lib/i18n";

// Le lien de démonstration vivait sur l'ancienne page d'accueil, qui redirige désormais
// ici. Sans ce report, `NEXT_PUBLIC_DEMO_PATH` serait restée configurée et sans effet —
// une variable muette que personne n'aurait vue s'éteindre.
const DEMO_PATH = process.env.NEXT_PUBLIC_DEMO_PATH;

// Where to land after login: honour a ?next= destination if it's a safe internal path, else the
// dashboard. Only same-origin relative paths are allowed — reject protocol-relative or absolute
// URLs so ?next= can't be turned into an open redirect. Exported for unit testing.
export function safeNextPath(raw: string | null): string {
  if (raw && raw.startsWith("/") && !raw.startsWith("//") && !raw.startsWith("/\\")) return raw;
  return "/dashboard";
}

function safeNext(): string {
  if (typeof window === "undefined") return "/dashboard";
  return safeNextPath(new URLSearchParams(window.location.search).get("next"));
}

export default function LoginPage() {
  const t = useT();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [ssoEnabled, setSsoEnabled] = useState(false);

  useEffect(() => {
    // Only offer SSO if the backend has a provider configured. Also surface a failed SSO round-trip.
    getAuthConfig()
      .then((c) => setSsoEnabled(c.oidc_enabled))
      .catch(() => setSsoEnabled(false));
    const params = new URLSearchParams(window.location.search);
    if (params.get("sso_error")) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setError(t("login.errSso"));
      history.replaceState(null, "", window.location.pathname);
    } else if (params.get("reason") === "password-changed") {
      // Changing a password ends every session, this one included. Say so, or being bounced to
      // the login page right after a successful save reads as the save having failed.
      setError(t("login.passwordChanged"));
      history.replaceState(null, "", window.location.pathname);
    }
  }, [t]);

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
          <p>
            {t("login.newHere")}{" "}
            <Link href="/register" className={lienDePied}>
              {t("login.create")}
            </Link>
          </p>
          <p className="mt-1.5">
            <Link href="/forgot-password" className={lienDePied}>
              {t("forgot.title")}
            </Link>
          </p>
          {DEMO_PATH && (
            <p className="mt-1.5">
              <Link href={DEMO_PATH} className={lienDePied}>
                {t("landing.tryDemo")}
              </Link>
            </p>
          )}
        </>
      }
    >
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
        <Champ label={t("common.password")}>
          <input
            required
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={inputClass}
          />
        </Champ>
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button type="submit" disabled={submitting} className={primaryButtonClass}>
          {submitting ? t("login.submitting") : t("login.title")}
        </button>
        {ssoEnabled && (
          <>
            <div className="flex items-center gap-3 py-1 text-xs text-muted">
              <span className="h-px flex-1 bg-border" />
              {t("common.or")}
              <span className="h-px flex-1 bg-border" />
            </div>
            <button
              type="button"
              onClick={beginOidcLogin}
              className="rounded-pill border border-border-strong px-4 py-2 text-sm font-medium text-foreground transition hover:border-accent hover:text-accent"
            >
              {t("login.sso")}
            </button>
          </>
        )}
      </form>
    </AuthCard>
  );
}
