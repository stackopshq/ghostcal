"use client";

import Link from "next/link";
import { useState } from "react";
import AuthCard, { inputClass, primaryButtonClass } from "@/components/AuthCard";
import { ApiError } from "@/lib/api";
import { register } from "@/lib/auth";

export default function RegisterPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await register(email, name, password);
      setDone(true);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? "That email is already registered."
          : "Could not create the account. Check your details and try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (done) {
    return (
      <AuthCard
        title="Check your inbox"
        subtitle={`We sent a verification link to ${email}. Confirm it to activate your account.`}
        footer={<Link href="/login" className="text-accent hover:underline">Back to sign in</Link>}
      >
        <p className="text-sm text-muted">
          The link expires in 24 hours. You can close this tab.
        </p>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Create your account"
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="text-accent hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form className="flex flex-col gap-3" onSubmit={onSubmit}>
        <input
          required
          placeholder="Your name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className={inputClass}
        />
        <input
          required
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className={inputClass}
        />
        <input
          required
          type="password"
          minLength={8}
          placeholder="Password (min 8 characters)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={inputClass}
        />
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button type="submit" disabled={submitting} className={primaryButtonClass}>
          {submitting ? "Creating…" : "Create account"}
        </button>
      </form>
    </AuthCard>
  );
}
