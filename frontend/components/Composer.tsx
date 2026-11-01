"use client";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";

type Attached = { id: string; filename: string };
export type RunOptions = { fileIds: string[]; priority: string };

export default function Composer({ initial, busy, token, onSubmit }: { initial: string; busy: boolean; token: string | null; onSubmit: (t: string, o: RunOptions) => void }) {
  const [text, setText] = useState(initial), [files, setFiles] = useState<Attached[]>([]), [priority, setPriority] = useState("balanced");
  const [more, setMore] = useState(false), [err, setErr] = useState(""), input = useRef<HTMLInputElement>(null);
  useEffect(() => setText(initial), [initial]);
  const ok = text.trim().length >= 3 && !busy;
  const submit = () => { if (ok) { onSubmit(text.trim(), { fileIds: files.map((f) => f.id), priority }); setFiles([]); } };

  async function attach(list: FileList | null) {
    setErr("");
    for (const f of Array.from(list ?? []).slice(0, 5 - files.length)) {
      const fd = new FormData(); fd.append("file", f);
      try {
        const res = await fetch("/api/files", { method: "POST", body: fd, headers: { Authorization: `Bearer ${token}` }, credentials: "include" });
        const d = await res.json();
        if (!res.ok) throw new ApiError(res.status, d.detail ?? "Upload failed.");
        setFiles((x) => [...x, d]);
      } catch (e) { setErr(e instanceof Error ? e.message : "The file wasn't attached."); }
    }
    if (input.current) input.current.value = "";
  }
  return (
    <div className="rounded-panel border border-line bg-panel p-4">
      <label htmlFor="objective" className="mb-2 block text-lg font-bold tracking-tight">What do you want to get done?</label>
      <textarea id="objective" value={text} onChange={(e) => setText(e.target.value)} rows={3} onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") submit(); }}
        placeholder="Describe the outcome you want. Flow.io plans it and runs it." className="w-full rounded-input border border-line bg-sunk px-3 py-2 text-base" />
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button onClick={submit} disabled={!ok} className="rounded-action bg-acc px-5 py-2.5 font-semibold text-accink disabled:opacity-50">{busy ? "Working" : "Run"}</button>
        <button onClick={() => setMore(!more)} aria-expanded={more} className="text-sm underline">{more ? "Fewer options" : "More options"}</button>
      </div>
      {more && (
        <div className="mt-3 space-y-3 rounded-input border border-line bg-sunk p-3 text-sm">
          <div>
            <label htmlFor="prio" className="mr-2">Favor</label>
            <select id="prio" value={priority} onChange={(e) => setPriority(e.target.value)} className="rounded-input border border-line bg-panel px-2 py-1">
              <option value="balanced">Balanced</option><option value="quality">Quality</option><option value="fast">Speed</option><option value="cheap">Low cost</option>
            </select>
          </div>
          <div>
            <label htmlFor="files" className="block">Attach text files (.txt, .md, .csv, .json; up to 5)</label>
            <input id="files" ref={input} type="file" multiple accept=".txt,.md,.csv,.json" onChange={(e) => attach(e.target.files)} className="mt-1" />
            {files.length > 0 && <ul className="mt-1.5 flex flex-wrap gap-1.5">{files.map((f) => <li key={f.id} className="rounded-full border border-line bg-panel px-2.5 py-0.5">{f.filename} <button aria-label={`Remove ${f.filename}`} onClick={() => setFiles(files.filter((x) => x.id !== f.id))}>x</button></li>)}</ul>}
            {err && <p role="alert" className="mt-1 text-bad">{err}</p>}
          </div>
        </div>
      )}
    </div>
  );
}
