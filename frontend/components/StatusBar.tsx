"use client";

import { STATUS_LABEL, type Task } from "@/lib/types";

export default function StatusBar({ task }: { task: Task | null }) {
  return (
    <footer
      className="fixed inset-x-0 bottom-0 z-20 box-border w-full max-w-full overflow-hidden border-t border-line bg-panel px-4 py-2 text-sm"
      style={{ paddingBottom: "max(0.5rem, env(safe-area-inset-bottom))" }}
    >
      {task ? (
        <p className="min-w-0 max-w-full break-words [overflow-wrap:anywhere]">
          Context items: {task.context_count}. Tools used:{" "}
          {task.tools_used.length ? task.tools_used.join(", ") : "none yet"}.
          {" "}Status: {STATUS_LABEL[task.status] ?? task.status}.
        </p>
      ) : (
        <p className="min-w-0 max-w-full break-words text-mute">
          No task selected. Create one to see its context, tools and status here.
        </p>
      )}
    </footer>
  );
}
