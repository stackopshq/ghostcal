"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import AuthCard from "@/components/AuthCard";
import { verifyEmail } from "@/lib/auth";

type Status = "verifying" | "ok" | "error";

function VerifyInner() {
  const token = useSearchParams().get("token");
  const [status, setStatus] = useState<Status>(token ? "verifying" : "error");

  useEffect(() => {
    if (!token) return;
    verifyEmail(token)
      .then(() => setStatus("ok"))
      .catch(() => setStatus("error"));
  }, [token]);

  if (status === "verifying") {
    return <AuthCard title="Verifying your email…"><p className="text-sm text-muted">One moment.</p></AuthCard>;
  }
  if (status === "ok") {
    return (
      <AuthCard
        title="Email verified ✓"
        subtitle="Your account is active."
        footer={<Link href="/login" className="text-accent hover:underline">Sign in</Link>}
      >
        <p className="text-sm text-muted">You can now sign in to GhostCal.</p>
      </AuthCard>
    );
  }
  return (
    <AuthCard
      title="Verification failed"
      subtitle="This link is invalid or has expired."
      footer={<Link href="/register" className="text-accent hover:underline">Create a new account</Link>}
    >
      <p className="text-sm text-muted">Request a fresh verification link by signing up again.</p>
    </AuthCard>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<AuthCard title="Verifying your email…"><p className="text-sm text-muted">One moment.</p></AuthCard>}>
      <VerifyInner />
    </Suspense>
  );
}
