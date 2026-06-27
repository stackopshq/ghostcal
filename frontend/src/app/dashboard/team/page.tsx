"use client";

import { useEffect, useState } from "react";
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

const ROLES = ["member", "admin", "owner"];

export default function TeamPage() {
  const [members, setMembers] = useState<Member[]>([]);
  const [invites, setInvites] = useState<Invitation[]>([]);
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([listMembers(), listInvitations().catch(() => [])])
      .then(([m, i]) => {
        if (!active) return;
        setMembers(m);
        setInvites(i);
      })
      .catch(() => active && setError("Could not load the team."))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [refresh]);

  function reload() {
    setRefresh((r) => r + 1);
  }

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await inviteMember(inviteEmail.trim(), inviteRole);
      setInviteEmail("");
      reload();
    } catch {
      setError("Could not send the invitation (already a member or invited?).");
    }
  }

  async function onRole(userId: string, role: string) {
    setError(null);
    try {
      setMembers(await changeRole(userId, role));
    } catch {
      setError("You can't change that member's role.");
    }
  }

  async function onRemove(userId: string) {
    if (!confirm("Remove this member from the organization?")) return;
    try {
      await removeMember(userId);
      reload();
    } catch {
      setError("You can't remove that member.");
    }
  }

  async function onRevoke(id: string) {
    await revokeInvitation(id);
    reload();
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-8 p-6 sm:p-10">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Team</h1>
        <p className="mt-1 text-sm text-muted">Manage members and invitations.</p>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}
      {loading && <p className="text-sm text-muted">Loading…</p>}

      {!loading && (
        <>
          <section className="flex flex-col gap-3">
            <h2 className="text-sm font-medium text-foreground">Members</h2>
            {members.map((m) => (
              <div
                key={m.user_id}
                className="glass flex items-center justify-between gap-3 rounded-xl p-4"
              >
                <div>
                  <p className="font-medium text-foreground">{m.name}</p>
                  <p className="text-sm text-muted">{m.email}</p>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    value={m.role}
                    onChange={(e) => onRole(m.user_id, e.target.value)}
                    className="rounded-lg border border-border-strong bg-surface-2 px-2 py-1.5 text-sm text-foreground outline-none focus:border-accent"
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
                    className="rounded-lg border border-border-strong px-3 py-1.5 text-sm text-muted transition hover:border-red-400 hover:text-red-400"
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </section>

          <section className="flex flex-col gap-3">
            <h2 className="text-sm font-medium text-foreground">Invite a teammate</h2>
            <form onSubmit={invite} className="flex flex-col gap-3 sm:flex-row">
              <input
                required
                type="email"
                placeholder="teammate@example.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                className="flex-1 rounded-lg border border-border-strong bg-surface-2 px-4 py-2.5 text-sm text-foreground outline-none focus:border-accent"
              />
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value)}
                className="rounded-lg border border-border-strong bg-surface-2 px-3 py-2.5 text-sm text-foreground outline-none focus:border-accent"
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
              <button
                type="submit"
                className="rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink shadow-[0_0_18px_rgba(0,240,255,0.45)] transition hover:brightness-110"
              >
                Invite
              </button>
            </form>

            {invites.length > 0 && (
              <div className="flex flex-col gap-2">
                {invites.map((i) => (
                  <div
                    key={i.id}
                    className="flex items-center justify-between rounded-lg border border-border px-4 py-2.5 text-sm"
                  >
                    <span className="text-foreground">
                      {i.email} <span className="text-muted">· {i.role} · pending</span>
                    </span>
                    <button
                      type="button"
                      onClick={() => onRevoke(i.id)}
                      className="text-muted transition hover:text-red-400"
                    >
                      Revoke
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
