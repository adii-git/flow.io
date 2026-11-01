"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { FollowUp, Task } from "@/lib/types";

const IDEAS: Record<string, string[]> = {
  image: ["Make the colours brighter", "Try a different style", "Put it on a black background", "Make it more minimal"],
  code: ["Add comments to the code", "Add error handling", "Write tests for it"],
  default: ["Make it shorter", "Explain it in simpler words", "Add more detail", "Turn it into bullet points"],
};

/** Chat box under the result: keep talking to the same task to change or extend the answer. */
export default function FollowUpChat({
  task, token, running, version, onSend,
}: {
  task: Task;
  token: string | null;
  running: boolean;
  version: number;
  onSend: (message: string) => Promise<boolean>;
}) {
  const [items, setItems] = useState<FollowUp[]>([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const box = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api<FollowUp[]>(`/api/tasks/${task.id}/followups`, token).then(setItems).catch(() => setItems([]));
  }, [task.id, token, version]);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [items.length]);

  const busy = running || sending;
  const ideas = IDEAS[task.plan?.task_type ?? ""] ?? IDEAS.default;

  async function send() {
    const message = text.trim();
    if (!message || busy) return;
    setSending(true);
    // show the bubble right away; the server copy replaces it on the next load
    setItems((cur) => [...cur, { id: `local-${Date.now()}`, message, created_at: new Date().toISOString() }]);
    setText("");
    const ok = await onSend(message);
    if (!ok) {
      setItems((cur) => cur.filter((i) => !i.id.startsWith("local-")));
      setText(message); // nothing is lost if it failed
    }
    setSending(false);
  }

  return (
    <section aria-label="Continue this task" className="fx-rise min-w-0 rounded-panel border border-line bg-panel p-4 sm:p-5">
      <h2 className="text-lg font-bold tracking-tight">Continue this task</h2>
      <p className="mt-0.5 text-sm text-mute">Ask for a change or something new. Flow.io keeps everything so far and updates the result.</p>

      <ol className="mt-3 flex min-w-0 flex-col gap-2" aria-live="polite">
        <li className="max-w-[85%] self-end rounded-input border border-line bg-sunk px-3 py-2 text-sm">
          <span className="block text-xs text-mute">You · first ask</span>
          {task.objective}
        </li>
        {items.map((m, i) => (
          <li key={m.id} className="fx-rise max-w-[85%] self-end rounded-input border border-acc bg-sunk px-3 py-2 text-sm">
            <span className="block text-xs text-mute">You · change {i + 1}</span>
            {m.message}
          </li>
        ))}
        {busy && (
          <li className="fx-rise self-start rounded-input border border-line px-3 py-2 text-sm text-mute">
            <span className="fx-typing" aria-label="Flow.io is working"><i /><i /><i /></span>
          </li>
        )}
      </ol>
      <div ref={end} />

      <div className="mt-3 flex flex-wrap gap-1.5">
        {ideas.map((idea) => (
          <button
            key={idea}
            type="button"
            disabled={busy}
            onClick={() => { setText(idea); box.current?.focus(); }}
            className="rounded-full border border-line bg-sunk px-3 py-1 text-xs disabled:opacity-50"
          >
            {idea}
          </button>
        ))}
      </div>

      <form
        className="mt-3 flex min-w-0 items-end gap-2"
        onSubmit={(e) => { e.preventDefault(); send(); }}
      >
        <label htmlFor="followup" className="sr-only">Your message</label>
        <textarea
          id="followup"
          ref={box}
          rows={1}
          value={text}
          maxLength={2000}
          disabled={busy}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
          }}
          placeholder={busy ? "Working on it…" : "e.g. make the background blue, or now write an Instagram caption"}
          className="max-h-40 min-h-[44px] min-w-0 flex-1 resize-y rounded-input border border-line bg-sunk p-2.5 text-sm"
        />
        <button
          type="submit"
          disabled={busy || !text.trim()}
          className="rounded-action bg-acc px-4 py-2.5 text-sm font-semibold text-accink disabled:opacity-50"
        >
          {busy ? "Working…" : "Send"}
        </button>
      </form>
      <p className="mt-1 text-xs text-mute">Enter to send · Shift+Enter for a new line</p>
    </section>
  );
}
