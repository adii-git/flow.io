"use client";

import { useState } from "react";
import { STEP_LABEL, type ContextTransfer, type Task } from "@/lib/types";
import LiveRoute from "./LiveRoute";
import Sheet from "./Sheet";
import StepDetail from "./StepDetail";

export default function TaskCanvas({
  task,
  transfers,
}: {
  task: Task;
  transfers: ContextTransfer[];
}) {
  const [open, setOpen] = useState<string | null>(null);

  const last = task.subtasks.length - 1;
  const step = task.subtasks.find((s) => s.id === open);
  const planned = task.status !== "draft";

  return (
    <section
      aria-label="Task steps"
      className="fx-rise box-border w-full min-w-0 max-w-full overflow-hidden rounded-panel border border-line bg-panel p-4 sm:p-5"
    >
      <h2 className="break-words text-2xl font-bold tracking-tight">
        {task.plan?.title ?? task.objective}
      </h2>

      <p className="mt-1 break-words text-mute">{task.objective}</p>

      {planned ? (
        <div className="mt-4 w-full min-w-0 max-w-full">
          <LiveRoute steps={task.subtasks} />
        </div>
      ) : (
        <p className="mt-2 break-words text-sm text-mute">
          Steps are outlined from keywords in your objective. Press Run to pick
          tools.
        </p>
      )}

      <ol className="mt-5 flex w-full min-w-0 max-w-full flex-col gap-4 md:flex-row md:flex-wrap md:gap-4">
        {task.subtasks.map((s, i) => {
          const live = s.status === "running";
          const skipped = s.status === "skipped";

          return (
            <li
              key={s.id}
              className="fx-rise relative box-border w-full min-w-0 max-w-full md:w-[calc(50%-0.5rem)] lg:w-[calc(33.333%-0.75rem)]"
              style={{ animationDelay: `${Math.min(i, 6) * 70}ms` }}
            >
              <button
                type="button"
                onClick={() => setOpen(s.id)}
                aria-label={`Step ${i + 1}, ${s.label}, ${STEP_LABEL[s.status] ?? s.status}. Open details`}
                className={`fx-step ${live ? "fx-running" : ""} ${s.status === "done" ? "fx-done" : ""} box-border h-full w-full min-w-0 max-w-full rounded-input border bg-sunk p-3 text-left ${
                  live
                    ? "border-2 border-acc"
                    : s.status === "failed"
                      ? "border-bad"
                      : planned
                        ? "border-line"
                        : "border-dashed border-line"
                } ${skipped ? "opacity-60" : ""}`}
              >
                <span className="flex min-w-0 flex-wrap justify-between gap-x-2 gap-y-1 text-sm text-mute">
                  <span>Step {i + 1}</span>
                  <span className="fx-badge">
                    <span className="fx-dot" aria-hidden="true" />
                    {STEP_LABEL[s.status] ?? s.status}
                  </span>
                </span>

                <span className="mt-1 block break-words font-semibold">
                  {s.label}
                </span>

                <span className="mt-1 block break-words text-sm">
                  {s.description}
                </span>

                <span className="mt-2 block break-words text-sm text-mute">
                  {skipped
                    ? "Skipped"
                    : s.routing?.tool_name
                      ? `Tool: ${s.routing.tool_name}`
                      : "Tool: chosen when you run"}
                </span>

                {s.output_preview && s.status === "done" && (
                  <span className="mt-1 block break-words text-sm text-mute">
                    {s.output_preview}
                  </span>
                )}
              </button>

              {i < last && (
                <span
                  aria-hidden="true"
                  className="absolute bg-line max-md:-bottom-4 max-md:left-6 max-md:h-4 max-md:w-px"
                />
              )}
            </li>
          );
        })}
      </ol>

      {step && (
        <Sheet
          title={`Step ${step.position + 1}: ${step.label}`}
          onClose={() => setOpen(null)}
        >
          <StepDetail step={step} transfers={transfers} />
        </Sheet>
      )}
    </section>
  );
}
