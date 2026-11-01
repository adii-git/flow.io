"use client";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

export type User = { id: string; email: string; display_name: string };
type AuthOut = { access_token: string; expires_in: number; user: User };
type Ctx = {
  user: User | null; loading: boolean; token: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, name: string) => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthCtx = createContext<Ctx | null>(null);

async function call(path: string, body?: unknown): Promise<AuthOut> {
  const res = await fetch(path, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const d = await res.json().catch(() => null);
    const detail = typeof d?.detail === "string" ? d.detail
      : res.status === 422 ? "Check the email address and use a password of at least 10 characters."
      : "Flow.io couldn't reach the server. Try again in a moment.";
    throw new Error(detail);
  }
  return res.json();
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null); // memory only, never localStorage
  const [loading, setLoading] = useState(true);
  const apply = useCallback((a: AuthOut | null) => { setUser(a?.user ?? null); setToken(a?.access_token ?? null); }, []);

  useEffect(() => {
    call("/api/auth/refresh").then(apply).catch(() => apply(null)).finally(() => setLoading(false));
  }, [apply]);

  useEffect(() => { // refresh shortly before the access token expires
    if (!token) return;
    const id = setInterval(() => call("/api/auth/refresh").then(apply).catch(() => apply(null)), 10 * 60 * 1000);
    return () => clearInterval(id);
  }, [token, apply]);

  const value: Ctx = {
    user, token, loading,
    signIn: async (email, password) => apply(await call("/api/auth/login", { email, password })),
    signUp: async (email, password, display_name) => apply(await call("/api/auth/register", { email, password, display_name })),
    signOut: async () => { await fetch("/api/auth/logout", { method: "POST", credentials: "include" }); apply(null); },
  };
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth(): Ctx {
  const c = useContext(AuthCtx);
  if (!c) throw new Error("useAuth must be used inside AuthProvider");
  return c;
}
