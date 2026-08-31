"use client";

import { useEffect, useState } from "react";
import { getActiveOrg, setActiveOrg } from "@/lib/auth";
import { useT } from "@/lib/i18n";
import { getMyOrganizations, type OrgMembership } from "@/lib/organization";

export default function OrgSwitcher() {
  const t = useT();
  const [orgs, setOrgs] = useState<OrgMembership[]>([]);
  const [active, setActive] = useState("");

  useEffect(() => {
    let on = true;
    getMyOrganizations()
      .then((list) => {
        if (!on) return;
        setOrgs(list);
        setActive(getActiveOrg() ?? list[0]?.id ?? "");
      })
      .catch(() => {});
    return () => {
      on = false;
    };
  }, []);

  if (orgs.length < 2) return null;

  return (
    <label className="mb-4 flex flex-col gap-1 px-1">
      <span className="text-2xs uppercase tracking-wide text-muted/70">
        {t("dash.organization")}
      </span>
      <select
        value={active}
        onChange={(e) => {
          setActiveOrg(e.target.value);
          window.location.reload();
        }}
        className="rounded-lg border border-border-strong bg-surface px-2 py-1.5 text-sm text-foreground outline-none focus:border-accent"
      >
        {orgs.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name} · {o.role}
          </option>
        ))}
      </select>
    </label>
  );
}
