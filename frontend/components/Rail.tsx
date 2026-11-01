"use client";
import { useState } from "react";
import type { Project, TaskSummary } from "@/lib/types";

type Props = {
  projects: Project[]; tasks: TaskSummary[]; activeProject: string | null; selected: string | null;
  onProject: (id: string | null) => void; onSelect: (id: string) => void;
  onNewProject: (name: string) => void; onDelete: (id: string) => void;
};

export default function Rail(p: Props) {
  const [name, setName] = useState("");
  const pill = (on: boolean) => `rounded-full border px-3 py-1 text-sm ${on ? "border-ink bg-ink text-bg" : "border-line bg-sunk"}`;
  return (
    <nav aria-label="Projects and history" className="space-y-5">
      <div>
        <h2 className="mb-2 text-sm font-semibold">Projects</h2>
        <div className="flex flex-wrap gap-2">
          <button aria-pressed={p.activeProject === null} onClick={() => p.onProject(null)} className={pill(p.activeProject === null)}>All tasks</button>
          {p.projects.map((pr) => (
            <button key={pr.id} aria-pressed={p.activeProject === pr.id} onClick={() => p.onProject(pr.id)} className={pill(p.activeProject === pr.id)}>{pr.name}</button>
          ))}
        </div>
        <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (name.trim()) { p.onNewProject(name.trim()); setName(""); } }}>
          <label htmlFor="np" className="sr-only">New project name</label>
          <input id="np" value={name} onChange={(e) => setName(e.target.value)} placeholder="New project"
            className="w-full rounded-input border border-line bg-sunk px-2 py-1 text-sm" />
          <button className="rounded-full border border-line bg-sunk px-3 py-1 text-sm">Add</button>
        </form>
      </div>
      <div>
        <h2 className="mb-2 text-sm font-semibold">History</h2>
        {p.tasks.length === 0 ? (
          <p className="text-sm text-mute">No tasks here yet. Describe an objective and press Create task.</p>
        ) : (
          <ul className="space-y-1">
            {p.tasks.map((t) => (
              <li key={t.id} className="flex items-center gap-1">
                <button onClick={() => p.onSelect(t.id)} aria-current={p.selected === t.id}
                  className={`flex-1 truncate rounded-input px-2 py-1.5 text-left text-sm ${p.selected === t.id ? "bg-sunk font-semibold" : ""}`}>{t.title}</button>
                <button aria-label={`Delete task ${t.title}`} onClick={() => p.onDelete(t.id)} className="px-2 text-sm text-mute">Delete</button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </nav>
  );
}
