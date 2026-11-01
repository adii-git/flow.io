"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { useAuth } from "@/lib/auth";

export default function AuthForm({ mode }: { mode: "login" | "register" }) {
  const { signIn, signUp } = useAuth();
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const reg = mode === "register";

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true); setError("");
    try {
      const email = String(f.get("email")), password = String(f.get("password"));
      if (reg) await signUp(email, password, String(f.get("name") || "")); else await signIn(email, password);
      router.push("/app");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something didn't work. Try again.");
      setBusy(false);
    }
  }

  const field = "w-full rounded-input border border-line bg-sunk px-3 py-3 text-base";
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4">
      <form onSubmit={submit} className="rounded-panel border border-line bg-panel p-6" aria-describedby={error ? "err" : undefined}>
        <h1 className="mb-5 text-3xl font-bold tracking-tight">{reg ? "Create your account" : "Sign in to Flow.io"}</h1>
        {reg && (<><label htmlFor="name" className="mb-1 block text-sm">Name</label>
          <input id="name" name="name" autoComplete="name" className={`${field} mb-3`} /></>)}
        <label htmlFor="email" className="mb-1 block text-sm">Email</label>
        <input id="email" name="email" type="email" required autoComplete="email" className={`${field} mb-3`} />
        <label htmlFor="password" className="mb-1 block text-sm">Password{reg && " (at least 10 characters)"}</label>
        <input id="password" name="password" type="password" required minLength={reg ? 10 : 1}
          autoComplete={reg ? "new-password" : "current-password"} className={`${field} mb-4`} />
        {error && <p id="err" role="alert" className="mb-3 text-sm text-bad">{error}</p>}
        <button disabled={busy} className="rounded-action bg-acc px-5 py-3 font-semibold text-accink disabled:opacity-60">
          {busy ? (reg ? "Creating account" : "Signing in") : (reg ? "Create account" : "Sign in")}
        </button>
        <p className="mt-4 text-sm text-mute">
          {reg ? "Already have an account? " : "New to Flow.io? "}
          <Link href={reg ? "/login" : "/register"} className="underline">{reg ? "Sign in" : "Create an account"}</Link>
        </p>
      </form>
    </main>
  );
}
