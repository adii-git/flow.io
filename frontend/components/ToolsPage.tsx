"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { CAP_LABEL, PROVIDER_LABEL, type Connection, type Tool } from "@/lib/types";

const STATUS = { ready: "Ready", needs_key: "Needs a key", planned: "Coming later" } as const;

export default function ToolsPage() {
  const { user, token, loading } = useAuth();
  const router = useRouter();
  const [tools, setTools] = useState<Tool[]>([]);
  const [conns, setConns] = useState<Connection[]>([]);
  const [problem, setProblem] = useState<{ what: string; details: string } | null>(null);
  const [saving, setSaving] = useState("");
  const [usage, setUsage] = useState<{ tasks: number; calls: number; tokens_in: number; tokens_out: number; days: number } | null>(null);

  useEffect(() => { if (!loading && !user) router.replace("/login"); }, [loading, user, router]);
  const fail = (what: string, e: unknown) => setProblem({ what, details: e instanceof ApiError ? `Status ${e.status}: ${e.message}` : String(e) });
  const load = useCallback(async () => {
    try { setTools(await api<Tool[]>("/api/tools", token)); setConns(await api<Connection[]>("/api/tools/connections", token)); }
    catch (e) { fail("Flow.io couldn't load the tool list. Reload to try again.", e); }
  }, [token]);
  useEffect(() => { if (token) { load(); api<typeof usage>("/api/usage", token).then(setUsage).catch(() => {}); } }, [token, load]);

  async function save(provider: string, e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget, key = String(new FormData(form).get("key") || "");
    setSaving(provider); setProblem(null);
    try { await api("/api/tools/connect", token, { method: "POST", body: JSON.stringify({ provider, api_key: key }) }); form.reset(); await load(); }
    catch (err) { fail("The key wasn't saved. Nothing changed, and the old key (if any) still applies.", err); }
    finally { setSaving(""); }
  }
  async function remove(provider: string) {
    try { await api<void>(`/api/tools/connect/${provider}`, token, { method: "DELETE" }); await load(); }
    catch (err) { fail("The key wasn't removed. It is still saved.", err); }
  }

  if (loading || !user) return <main className="p-6 text-mute">Checking your session</main>;
  const providers = Array.from(new Set(tools.map((t) => t.provider)));
  return (
    <div className="mx-auto max-w-3xl px-4 py-6">
      <header className="mb-4 flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight">Tools</h1>
        <Link href="/app" className="rounded-full border border-line bg-panel px-4 py-1.5 text-sm">Back to workspace</Link>
      </header>
      <p className="mb-5 text-mute">Keys are stored encrypted and never shown again. A saved key isn't checked until a task uses it, and a rejected key shows up as a failed step with a plain explanation.</p>
      {usage && <p className="mb-4 text-sm text-mute">Last {usage.days} days: {usage.tasks} tasks, {usage.calls} tool calls, {usage.tokens_in.toLocaleString()} tokens in and {usage.tokens_out.toLocaleString()} out. Cost isn't calculated yet.</p>}
      {problem && (
        <div role="alert" className="mb-4 rounded-input border border-bad bg-panel p-3 text-sm">
          <p className="font-semibold text-bad">{problem.what}</p>
          <details className="mt-1"><summary className="cursor-pointer">View details</summary><p className="mt-1 text-mute">{problem.details}</p></details>
        </div>
      )}
      {tools.length === 0 && !problem && <p className="text-mute">Loading the tool list</p>}
      <div className="space-y-5">
        {providers.map((p) => {
          const list = tools.filter((t) => t.provider === p), conn = conns.find((c) => c.provider === p), needsKey = list.some((t) => t.requires_key);
          return (
            <section key={p} aria-labelledby={`h-${p}`} className="rounded-panel border border-line bg-panel p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 id={`h-${p}`} className="text-xl font-bold">{PROVIDER_LABEL[p] ?? p}</h2>
                {needsKey && (conn
                  ? <p className="text-sm">Key saved, ends in {conn.key_hint} <button onClick={() => remove(p)} className="ml-2 underline">Remove key</button></p>
                  : <p className="text-sm text-mute">No key saved</p>)}
              </div>
              {needsKey && (
                <form onSubmit={(e) => save(p, e)} className="mt-3 flex gap-2">
                  <label htmlFor={`k-${p}`} className="sr-only">{PROVIDER_LABEL[p] ?? p} API key</label>
                  <input id={`k-${p}`} name="key" type="password" required minLength={8} autoComplete="off" spellCheck={false}
                    placeholder={conn ? "Paste a new key to replace it" : "Paste your API key"} className="w-full rounded-input border border-line bg-sunk px-3 py-2 text-sm" />
                  <button disabled={saving === p} className="rounded-action bg-acc px-4 py-2 text-sm font-semibold text-accink disabled:opacity-60">{saving === p ? "Saving" : "Save key"}</button>
                </form>
              )}
              <ul className="mt-4 space-y-3">
                {list.map((t) => (
                  <li key={t.id} className="rounded-input border border-line bg-sunk p-3">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <p className="font-semibold">{t.name}</p>
                      <p className="text-sm text-mute">{STATUS[t.status]}</p>
                    </div>
                    <p className="text-sm">{t.summary}</p>
                    <p className="mt-1 text-sm text-mute">{t.capabilities.map((c) => CAP_LABEL[c] ?? c).join(", ")}. Speed: {t.speed_class}. Cost: {t.cost_class}.</p>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </div>
  );
}
