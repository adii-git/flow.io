"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Run = { task_id: string; status: string; duration_ms: number | null; tools: string[]; tokens_in: number; tokens_out: number; retries: number; failures: number; context_chars: number };
type Lat = { tool: string; calls: number; p50: number | null; p95: number | null };

export default function Admin() {
  const { user, token, loading } = useAuth(), router = useRouter();
  const [d, setD] = useState<{ runs: Run[]; provider_latency_ms: Lat[] } | null>(null), [err, setErr] = useState("");
  useEffect(() => { if (!loading && !user) router.replace("/login"); }, [loading, user, router]);
  useEffect(() => { if (token) api<typeof d>("/api/admin/metrics", token).then(setD).catch((e) => setErr(e instanceof ApiError && e.status === 403 ? "This page is for Flow.io admins. Ask an admin to add your email to ADMIN_EMAILS." : "Metrics couldn't load. Reload to try again.")); }, [token]);
  const th = "px-2 py-1 text-left font-semibold";
  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      <header className="mb-4 flex items-center justify-between"><h1 className="text-3xl font-bold tracking-tight">Run metrics</h1><Link href="/app" className="rounded-full border border-line bg-panel px-4 py-1.5 text-sm">Back to workspace</Link></header>
      {err && <p role="alert" className="rounded-input border border-bad bg-panel p-3 text-sm">{err}</p>}
      {d && (<>
        <h2 className="mb-1 mt-4 text-xl font-bold">Recent runs</h2>
        <div className="overflow-x-auto rounded-input border border-line bg-panel"><table className="w-full text-sm"><thead><tr><th className={th}>Status</th><th className={th}>Duration</th><th className={th}>Tools</th><th className={th}>Tokens in/out</th><th className={th}>Retries</th><th className={th}>Failures</th><th className={th}>Context (chars)</th></tr></thead>
          <tbody>{d.runs.map((r) => <tr key={r.task_id} className="border-t border-line"><td className="px-2 py-1">{r.status}</td><td className="px-2 py-1">{r.duration_ms == null ? "n/a" : `${(r.duration_ms / 1000).toFixed(1)} s`}</td><td className="px-2 py-1">{r.tools.join(", ") || "none"}</td><td className="px-2 py-1">{r.tokens_in}/{r.tokens_out}</td><td className="px-2 py-1">{r.retries}</td><td className="px-2 py-1">{r.failures}</td><td className="px-2 py-1">{r.context_chars.toLocaleString()}</td></tr>)}</tbody></table></div>
        <h2 className="mb-1 mt-6 text-xl font-bold">Provider latency</h2>
        <div className="overflow-x-auto rounded-input border border-line bg-panel"><table className="w-full text-sm"><thead><tr><th className={th}>Tool</th><th className={th}>Calls</th><th className={th}>p50 (ms)</th><th className={th}>p95 (ms)</th></tr></thead>
          <tbody>{d.provider_latency_ms.map((l) => <tr key={l.tool} className="border-t border-line"><td className="px-2 py-1">{l.tool}</td><td className="px-2 py-1">{l.calls}</td><td className="px-2 py-1">{l.p50}</td><td className="px-2 py-1">{l.p95}</td></tr>)}</tbody></table></div>
      </>)}
    </div>
  );
}
