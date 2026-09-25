"use client";

import { useEffect, useState } from "react";
import { getActiveOrg } from "@/lib/auth";
import { useT } from "@/lib/i18n";
import {
  changeRole,
  inviteMember,
  Invitation,
  listInvitations,
  listMembers,
  Member,
  removeMember,
  revokeInvitation,
} from "@/lib/team";
import { getUnlockedKeys, wrapKeyForGrant } from "@/lib/zk";
import {
  KeyIcon,
} from "@/components/icons";

const ROLES = ["member", "admin", "owner"];

export default function TeamPage() {
  const t = useT();
  const [members, setMembers] = useState<Member[]>([]);
  const [invites, setInvites] = useState<Invitation[]>([]);
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [error, setError] = useState<string | null>(null);
  const [secureLink, setSecureLink] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([listMembers(), listInvitations().catch(() => [])])
      .then(([m, i]) => {
        if (!active) return;
        setMembers(m);
        setInvites(i);
      })
      .catch(() => active && setError(t("team.errLoad")))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refresh]);

  function reload() {
    setRefresh((r) => r + 1);
  }

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSecureLink(null);
    try {
      // If the org key is unlocked, seal it under a random grant key carried in the link fragment,
      // so the new member can decrypt invitee data once they accept (zero-knowledge team sharing).
      const keys = getUnlockedKeys(getActiveOrg());
      let wrappedOrgKey: string | null = null;
      let grantKey: string | null = null;
      if (keys) {
        const grant = await wrapKeyForGrant(keys.privateKey);
        wrappedOrgKey = grant.wrapped_org_key;
        grantKey = grant.grant_key;
      }
      const invitation = await inviteMember(inviteEmail.trim(), inviteRole, wrappedOrgKey);
      if (invitation.token && grantKey) {
        setSecureLink(`${window.location.origin}/invitations/${invitation.token}#k=${grantKey}`);
      }
      setInviteEmail("");
      reload();
    } catch {
      setError(t("team.errInvite"));
    }
  }

  async function onRole(userId: string, role: string) {
    setError(null);
    try {
      setMembers(await changeRole(userId, role));
    } catch {
      setError(t("team.errRole"));
    }
  }

  async function onRemove(userId: string) {
    if (!confirm(t("team.confirmRemove"))) return;
    try {
      await removeMember(userId);
      reload();
    } catch {
      setError(t("team.errRemove"));
    }
  }

  async function onRevoke(id: string) {
    await revokeInvitation(id);
    reload();
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-8 p-6 sm:p-10">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">{t("team.title")}</h1>
        <p className="mt-1 text-sm text-muted">{t("team.sub")}</p>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}
      {loading && <p className="text-sm text-muted">{t("common.loading")}</p>}

      {!loading && (
        <>
          <section className="flex flex-col gap-3">
            <h2 className="text-sm font-medium text-foreground">{t("team.members")}</h2>
            {members.map((m) => (
              <div
                key={m.user_id}
                className="glass flex items-center justify-between gap-3 rounded p-4"
              >
                <div>
                  <p className="font-medium text-foreground">{m.name}</p>
                  <p className="text-sm text-muted">{m.email}</p>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    value={m.role}
                    onChange={(e) => onRole(m.user_id, e.target.value)}
                    className="rounded border border-border-strong bg-surface-2 px-2 py-1.5 text-sm text-foreground outline-none focus:border-accent"
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => onRemove(m.user_id)}
                    className="rounded-pill border border-border-strong px-3 py-1.5 text-sm text-muted transition hover:border-red-400 hover:text-red-400"
                  >
                    {t("team.remove")}
                  </button>
                </div>
              </div>
            ))}
          </section>

          <section className="flex flex-col gap-3">
            <h2 className="text-sm font-medium text-foreground">{t("team.invite")}</h2>
            <form onSubmit={invite} className="flex flex-col gap-3 sm:flex-row">
              <input
                required
                type="email"
                placeholder="teammate@example.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                className="flex-1 rounded border border-border-strong bg-surface-2 px-4 py-2.5 text-sm text-foreground outline-none focus:border-accent"
              />
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value)}
                className="rounded border border-border-strong bg-surface-2 px-3 py-2.5 text-sm text-foreground outline-none focus:border-accent"
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
              <button
                type="submit"
                className="rounded-pill bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink shadow-[0_0_18px_color-mix(in_srgb,var(--color-accent)_45%,transparent)] transition hover:brightness-110"
              >
                {t("team.inviteBtn")}
              </button>
            </form>

            {secureLink && (
              <div className="rounded border border-accent/40 bg-surface-2/60 p-4">
                <p className="mb-1 flex items-center gap-1.5 text-sm font-medium text-accent">
                  <KeyIcon /> {t("team.secureLinkTitle")}
                </p>
                <p className="mb-2 text-xs text-muted">{t("team.secureLinkSub")}</p>
                <code className="block break-all rounded-lg bg-base/80 px-3 py-2 font-mono text-xs text-foreground">
                  {secureLink}
                </code>
                <button
                  type="button"
                  onClick={() => void navigator.clipboard?.writeText(secureLink)}
                  className="mt-2 text-xs text-accent hover:underline"
                >
                  {t("team.secureLinkCopy")}
                </button>
              </div>
            )}

            {invites.length > 0 && (
              <div className="flex flex-col gap-2">
                {invites.map((i) => (
                  <div
                    key={i.id}
                    className="flex items-center justify-between rounded-lg border border-border px-4 py-2.5 text-sm"
                  >
                    <span className="text-foreground">
                      {i.email}{" "}
                      <span className="text-muted">
                        · {i.role} · {t("team.pending")}
                      </span>
                    </span>
                    <button
                      type="button"
                      onClick={() => onRevoke(i.id)}
                      className="text-muted transition hover:text-red-400"
                    >
                      {t("team.revoke")}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </main>
  );
}
