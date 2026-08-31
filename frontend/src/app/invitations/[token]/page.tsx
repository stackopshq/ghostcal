"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getInvitationPreview, type InvitationPreview } from "@/lib/api";
import { isAuthenticated, setActiveOrg } from "@/lib/auth";
import { useT } from "@/lib/i18n";
import { acceptInvitation, storeMemberKey } from "@/lib/team";
import { rewrapForPassword, storeUnlockedKey, unwrapKeyFromGrant } from "@/lib/zk";

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
  const [password, setPassword] = useState("");
  // The decryption grant key rides in the URL fragment (#k=...), never sent to the server. Read it
  // once at mount; it has no setter.
  const [grantKey] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    const m = /[#&]k=([^&]+)/.exec(window.location.hash);
    return m ? decodeURIComponent(m[1]) : null;
  });

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

  // Whether this invite carries decryption access that we can unlock (needs the password to re-wrap).
  const hasGrant = Boolean(grantKey && preview?.wrapped_org_key);

  async function accept() {
    setAccepting(true);
    setError(null);
    try {
      const { organization_id } = await acceptInvitation(token);
      // Convert the grant: recover the org private key with the fragment key, re-wrap it under this
      // member's password, and persist it — so they can decrypt the team's invitee data.
      if (grantKey && preview?.wrapped_org_key && password) {
        const orgPrivateKey = await unwrapKeyFromGrant(grantKey, preview.wrapped_org_key);
        const wrapped = await rewrapForPassword(orgPrivateKey, password);
        await storeMemberKey(organization_id, wrapped.wrapped_private_key, wrapped.salt);
        storeUnlockedKey(organization_id, { publicKey: "", privateKey: orgPrivateKey });
      }
      setActiveOrg(organization_id); // land in the org you just joined
      router.push("/dashboard");
    } catch {
      setError(t("inv.errAccept"));
      setAccepting(false);
    }
  }

  return (
    <main className="flex flex-1 items-center justify-center p-4 sm:p-8">
      <div className="glass w-full max-w-md rounded-lg p-8 text-center shadow-2xl">
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
              <div className="mt-6 flex flex-col gap-3">
                {hasGrant && (
                  <div className="text-left">
                    <p className="mb-1 flex items-center gap-1.5 text-xs text-accent">
                      <span aria-hidden>🔑</span> {t("inv.unlockTitle")}
                    </p>
                    <input
                      type="password"
                      placeholder={t("inv.unlockPasswordPh")}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="w-full rounded border border-border-strong bg-surface-2 px-4 py-2.5 text-sm text-foreground outline-none focus:border-accent"
                    />
                  </div>
                )}
                <button
                  type="button"
                  onClick={accept}
                  disabled={accepting || (hasGrant && !password)}
                  className="w-full rounded-pill bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink shadow-[0_0_18px_color-mix(in_srgb,var(--color-accent)_45%,transparent)] transition hover:brightness-110 disabled:opacity-60"
                >
                  {accepting ? t("inv.joining") : t("inv.accept")}
                </button>
              </div>
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
