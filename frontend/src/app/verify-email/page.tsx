"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import AuthCard, { lienDePied } from "@/components/AuthCard";
import { verifyEmail } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type Status = "verifying" | "ok" | "error";

function VerifyInner() {
  const t = useT();
  const token = useSearchParams().get("token");
  const [status, setStatus] = useState<Status>(token ? "verifying" : "error");

  useEffect(() => {
    if (!token) return;
    verifyEmail(token)
      .then(() => setStatus("ok"))
      .catch(() => setStatus("error"));
  }, [token]);

  if (status === "verifying") {
    return (
      <AuthCard title={t("verify.verifying")}>
        <p className="text-sm text-muted">{t("verify.oneMoment")}</p>
      </AuthCard>
    );
  }
  if (status === "ok") {
    return (
      <AuthCard
        title={t("verify.okTitle")}
        subtitle={t("verify.okSub")}
        footer={
          <Link href="/login" className={lienDePied}>
            {t("common.signIn")}
          </Link>
        }
      >
        <p className="text-sm text-muted">{t("verify.okBody")}</p>
      </AuthCard>
    );
  }
  return (
    <AuthCard
      title={t("verify.failTitle")}
      subtitle={t("verify.failSub")}
      footer={
        <Link href="/register" className={lienDePied}>
          {t("verify.createNew")}
        </Link>
      }
    >
      <p className="text-sm text-muted">{t("verify.failBody")}</p>
    </AuthCard>
  );
}

function Loading() {
  const t = useT();
  return (
    <AuthCard title={t("verify.verifying")}>
      <p className="text-sm text-muted">{t("verify.oneMoment")}</p>
    </AuthCard>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<Loading />}>
      <VerifyInner />
    </Suspense>
  );
}
