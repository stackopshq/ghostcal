"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getInvitationPreview, type InvitationPreview } from "@/lib/api";
import { isAuthenticated, setActiveOrg } from "@/lib/auth";
import { useT } from "@/lib/i18n";
import { acceptInvitation } from "@/lib/team";

export default function InvitationPage() {
  const t = useT();
  const params = useParams<{ token: string }>();
  const token = params.token;
  const router = useRouter();
  const [preview, setPreview] = useState<InvitationPreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [authed, setAuthed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [accepting, setAccepting] = useState(false);

  useEffect(() => {
    let active = true;
    getInvitationPreview(token)
      .then((p) => active && setPreview(p))
      .catch(() => active && setPreview(null))
      .finally(() => {
        if (!active) return;
        setAuthed(isAuthenticated());
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [token]);

  async function accept() {
    setAccepting(true);
    setError(null);
    try {
      const { organization_id } = await acceptInvitation(token);
      setActiveOrg(organization_id); // land in the org you just joined
      router.push("/dashboard");
    } catch {
      setError(t("inv.errAccept"));
      setAccepting(false);
    }
  }

  return (
    <main className="flex flex-1 items-center justify-center p-4 sm:p-8">
      <div className="glass w-full max-w-md rounded-2xl p-8 text-center shadow-2xl">
        {loading ? (
          <p className="text-sm text-muted">{t("common.loading")}</p>
        ) : !preview ? (
          <>
            <h1 className="text-xl font-semibold text-foreground">{t("inv.notFound")}</h1>
            <p className="mt-2 text-sm text-muted">{t("inv.expired")}</p>
          </>
        ) : (
          <>
            <p className="text-sm text-muted">{t("inv.invitedToJoin")}</p>
            <h1 className="mt-1 text-2xl font-semibold text-foreground">
              {preview.organization_name}
            </h1>
            <p className="mt-2 text-sm text-muted">
              {t("inv.asRole", { role: preview.role, email: preview.email })}
            </p>

            {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

            {authed ? (
              <button
                type="button"
                onClick={accept}
                disabled={accepting}
                className="mt-6 w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink shadow-[0_0_18px_rgba(0,240,255,0.45)] transition hover:brightness-110 disabled:opacity-60"
              >
                {accepting ? t("inv.joining") : t("inv.accept")}
              </button>
            ) : (
              <div className="mt-6 flex flex-col gap-3">
                <p className="text-sm text-muted">
                  {t("inv.signinPrompt", { email: preview.email })}
                </p>
                <div className="flex gap-3">
                  <Link
                    href="/login"
                    className="flex-1 rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink transition hover:brightness-110"
                  >
                    {t("common.signIn")}
                  </Link>
                  <Link
                    href="/register"
                    className="flex-1 rounded-lg border border-border-strong px-4 py-2.5 text-sm text-foreground transition hover:border-accent hover:text-accent"
                  >
                    {t("inv.signUp")}
                  </Link>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}
