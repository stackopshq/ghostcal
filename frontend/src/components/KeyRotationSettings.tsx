"use client";

import { useEffect, useState } from "react";
import { getActiveOrg } from "@/lib/auth";
import { getMyOrganizations } from "@/lib/organization";
import {
  type MemberPublicKey,
  MembersNotReady,
  getMemberPublicKeys,
  membersWithoutKeys,
  rotateOrgKey,
} from "@/lib/keypair";
import { useT } from "@/lib/i18n";

/**
 * Rotate the organization's encryption key (ADR-0007).
 *
 * This is what makes removing a member actually revoke something: without it, the organization's
 * public key never changes, so everything created *after* they leave is still sealed to a key they
 * may have kept.
 */
export default function KeyRotationSettings() {
  const t = useT();
  const [members, setMembers] = useState<MemberPublicKey[] | null>(null);
  const [orgId, setOrgId] = useState<string | null>(null);
  const [rotating, setRotating] = useState(false);
  const [armed, setArmed] = useState(false);
  const [done, setDone] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    // The active org is only pinned in storage once you switch orgs or accept an invitation, so a
    // single-org account has none. Resolve it the way the rest of the dashboard does, or a rotation
    // would quietly do nothing for most people.
    Promise.all([getMemberPublicKeys(), getMyOrganizations()])
      .then(([m, orgs]) => {
        if (!active) return;
        setMembers(m);
        const current = orgs.find((o) => o.id === getActiveOrg()) ?? orgs[0];
        setOrgId(current?.id ?? null);
      })
      .catch(() => active && setError(t("common.errGeneric")));
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const notReady = members ? membersWithoutKeys(members) : [];

  async function rotate() {
    if (!orgId) {
      setError(t("common.errGeneric"));
      return;
    }
    setRotating(true);
    setError(null);
    try {
      setDone(await rotateOrgKey(orgId));
      setArmed(false);
      setMembers(await getMemberPublicKeys());
    } catch (err) {
      if (err instanceof MembersNotReady) {
        setError(
          t("rotation.errNotReady").replace(
            "{names}",
            err.members.map((m) => m.email).join(", "),
          ),
        );
      } else {
        setError(t("rotation.errFailed"));
      }
    } finally {
      setRotating(false);
    }
  }

  return (
    <section className="border-t border-border pt-6">
      <h2 className="text-lg font-semibold text-foreground">
        {t("rotation.title")}
      </h2>
      <p className="mt-1 text-sm text-muted">{t("rotation.sub")}</p>

      {notReady.length > 0 && (
        <p className="mt-3 rounded-lg border border-amber-500/40 bg-amber-500/5 px-4 py-3 text-sm text-amber-300">
          {t("rotation.notReady").replace(
            "{names}",
            notReady.map((m) => m.email).join(", "),
          )}
        </p>
      )}

      {!armed ? (
        <button
          type="button"
          onClick={() => setArmed(true)}
          disabled={members === null || orgId === null || notReady.length > 0}
          className="mt-4 rounded-lg border border-border px-4 py-2 text-sm font-medium text-foreground transition hover:bg-surface-2 disabled:opacity-40"
        >
          {t("rotation.rotate")}
        </button>
      ) : (
        <div className="mt-4 flex flex-col gap-3">
          <p className="rounded-lg border border-border bg-surface-2/50 px-4 py-3 text-sm text-muted">
            {t("rotation.confirm")}
          </p>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={rotate}
              disabled={rotating}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-black transition hover:opacity-90 disabled:opacity-40"
            >
              {rotating ? t("rotation.rotating") : t("rotation.confirmRotate")}
            </button>
            <button
              type="button"
              onClick={() => setArmed(false)}
              className="text-sm text-muted hover:text-foreground"
            >
              {t("common.cancel")}
            </button>
          </div>
        </div>
      )}

      {done !== null && (
        <p className="mt-3 text-sm text-accent">
          {t("rotation.done").replace("{n}", String(done))}
        </p>
      )}
      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
    </section>
  );
}
