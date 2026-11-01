
"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useTaskStream } from "@/lib/stream";

import type {
  ContextTransfer,
  PlanOut,
  Project,
  ResultPayload,
  Task,
  TaskEvent,
  TaskSummary,
} from "@/lib/types";

import Composer, { type RunOptions } from "./Composer";
import FollowUpChat from "./FollowUpChat";
import Rail from "./Rail";
import ResultView from "./Results";
import StatusBar from "./StatusBar";
import TaskCanvas from "./TaskCanvas";

type Problem = {
  what: string;
  doing: string;
  details: string;
  link?: { href: string; text: string };
};

export default function Workspace() {
  const { user, token, loading, signOut } = useAuth();
  const router = useRouter();
  const prefill = useSearchParams().get("objective") ?? "";

  const [projects, setProjects] = useState<Project[]>([]);
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [activeProject, setActiveProject] = useState<string | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [result, setResult] = useState<ResultPayload | null>(null);
  const [transfers, setTransfers] = useState<ContextTransfer[]>([]);
  const [log, setLog] = useState<TaskEvent[]>([]);
  const [live, setLive] = useState("");
  const [chatVersion, setChatVersion] = useState(0);
  const [streaming, setStreaming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [mode, setMode] = useState("live");
  const [notes, setNotes] = useState<string[]>([]);

  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  useEffect(() => {
    fetch("/api/config")
      .then((response) => response.json())
      .then((config) => setMode(config.execution_mode))
      .catch(() => {});
  }, []);

  const fail = (
    what: string,
    doing: string,
    error: unknown,
    link?: Problem["link"],
  ) => {
    setProblem({
      what,
      doing,
      link,
      details:
        error instanceof ApiError
          ? `Status ${error.status}: ${error.message}`
          : String(error),
    });
  };

  const loadTasks = useCallback(
    async (projectId: string | null) => {
      try {
        setTasks(
          await api<TaskSummary[]>(
            `/api/tasks${projectId ? `?project_id=${projectId}` : ""}`,
            token,
          ),
        );
      } catch (error) {
        fail(
          "Flow.io couldn't load your task history.",
          "Your tasks are safe. Reload the page to try again.",
          error,
        );
      }
    },
    [token],
  );

  useEffect(() => {
    if (!token) return;

    api<Project[]>("/api/projects", token)
      .then(setProjects)
      .catch((error) =>
        fail(
          "Flow.io couldn't load your projects.",
          "Reload the page to try again.",
          error,
        ),
      );

    loadTasks(activeProject);
  }, [token, activeProject, loadTasks]);

  const refresh = useCallback(
    async (id: string, full = false) => {
      try {
        const currentTask = await api<Task>(`/api/tasks/${id}`, token);
        setTask(currentTask);

        if (full || currentTask.status !== "running") {
          setTransfers(
            await api<ContextTransfer[]>(`/api/context/${id}`, token).catch(
              () => [],
            ),
          );

          setResult(
            currentTask.status === "done"
              ? await api<ResultPayload>(`/api/tasks/${id}/result`, token).catch(
                  () => null,
                )
              : null,
          );

          loadTasks(activeProject);
        }
      } catch (error) {
        fail(
          "Flow.io couldn't refresh this task.",
          "The run continues on the server. Reopen the task from History in a moment.",
          error,
        );
      }
    },
    [token, activeProject, loadTasks],
  );

  useTaskStream(
    streaming && task ? task.id : null,
    token,
    (event) => {
      // Live token deltas type out the current step; they bypass the activity log.
      if (event.type === "step.token") {
        setLive((current) => current + event.message);
        return;
      }

      // A new step starting or any step finishing clears the typing buffer.
      if (event.type === "step.started" || event.type.startsWith("step.")) {
        setLive("");
      }

      setLog((current) => [...current.slice(-40), event]);

      if (timer.current) clearTimeout(timer.current);

      timer.current = setTimeout(() => {
        if (task) refresh(task.id);
      }, 200);
    },
    () => {
      setStreaming(false);
      setLive("");
      setChatVersion((v) => v + 1);
      if (task) refresh(task.id, true);
    },
  );

  useEffect(() => {
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  async function run(objective: string, options: RunOptions) {
    setBusy(true);
    setProblem(null);
    setResult(null);
    setLog([]);
    setLive("");
    setNotes([]);
    setTransfers([]);

    let stage = "create the task";

    try {
      const createdTask = await api<Task>("/api/tasks", token, {
        method: "POST",
        body: JSON.stringify({
          objective,
          project_id: activeProject,
          file_ids: options.fileIds,
        }),
      });

      setTask(createdTask);

      if (prefill) {
        router.replace("/app");
      }

      stage = "plan the task";

      const plan = await api<PlanOut>(
        `/api/tasks/${createdTask.id}/plan`,
        token,
        {
          method: "POST",
          body: JSON.stringify({ priority: options.priority }),
        },
      );

      setTask(plan.task);
      setNotes(plan.notes);
      await loadTasks(activeProject);

      if (plan.blockers.length > 0) {
        setProblem({
          what: `This task needs a key for ${plan.blockers
            .map((blocker) => blocker.provider)
            .join(" and ")}.`,
          doing:
            "The plan is saved. Add the key in Tools, then press Run on this task again.",
          details: plan.blockers
            .map((blocker) => `${blocker.provider}: ${blocker.tools.join(", ")}`)
            .join("\n"),
          link: { href: "/tools", text: "Open Tools" },
        });

        return;
      }

      stage = "start the run";

      await api(`/api/tasks/${createdTask.id}/execute`, token, {
        method: "POST",
      });

      setLog([]);
      setStreaming(true);
    } catch (error) {
      fail(
        `Flow.io couldn't ${stage}.`,
        "Your text is kept. Nothing runs until the problem is fixed. Press Run to try again.",
        error,
      );
    } finally {
      setBusy(false);
    }
  }

  async function sendFollowUp(message: string): Promise<boolean> {
    if (!task) return false;
    setProblem(null);
    try {
      const out = await api<{ added_steps: string[]; notes: string[] }>(`/api/tasks/${task.id}/followup`, token, {
        method: "POST",
        body: JSON.stringify({ message }),
      });
      setNotes(out.notes ?? []);
      setResult(null);
      setLog([]);
      setLive("");
      await refresh(task.id);
      setStreaming(true);
      setChatVersion((v) => v + 1);
      return true;
    } catch (error) {
      fail(
        "Your message wasn't sent.",
        "Nothing changed. Check the message below, then try again.",
        error,
        error instanceof ApiError && error.status === 409 ? { href: "/tools", text: "Open Tools" } : undefined,
      );
      setChatVersion((v) => v + 1);
      return false;
    }
  }

  async function rerun() {
    if (!task) return;

    setBusy(true);
    setProblem(null);
    setResult(null);
    setLog([]);
    setLive("");

    try {
      await api(`/api/tasks/${task.id}/execute`, token, {
        method: "POST",
      });

      setStreaming(true);
    } catch (error) {
      fail(
        "The task didn't start.",
        "Nothing changed. Check Tools for keys, then try again.",
        error,
        { href: "/tools", text: "Open Tools" },
      );
    } finally {
      setBusy(false);
    }
  }

  async function select(id: string) {
    setStreaming(false);
    setProblem(null);
    setLog([]);
    setLive("");
    setNotes([]);

    await refresh(id, true);

    const selectedTask = await api<Task>(`/api/tasks/${id}`, token).catch(
      () => null,
    );

    if (selectedTask?.status === "running") {
      setStreaming(true);
    }
  }

  async function remove(id: string) {
    if (
      !window.confirm(
        "Delete this task and its steps? This can't be undone.",
      )
    ) {
      return;
    }

    try {
      await api<void>(`/api/tasks/${id}`, token, {
        method: "DELETE",
      });

      if (task?.id === id) {
        setTask(null);
        setResult(null);
      }

      await loadTasks(activeProject);
    } catch (error) {
      fail(
        "The task wasn't deleted.",
        "It is still in your history.",
        error,
      );
    }
  }

  async function newProject(name: string) {
    try {
      const project = await api<Project>("/api/projects", token, {
        method: "POST",
        body: JSON.stringify({ name }),
      });

      setProjects((current) => [...current, project]);
      setActiveProject(project.id);
    } catch (error) {
      fail(
        "The project wasn't created.",
        "Try a different name or try again.",
        error,
      );
    }
  }

  if (loading || !user) {
    return <main className="min-w-0 p-6 text-mute">Checking your session</main>;
  }

  const rail = (
    <Rail
      projects={projects}
      tasks={tasks}
      activeProject={activeProject}
      selected={task?.id ?? null}
      onProject={setActiveProject}
      onSelect={select}
      onNewProject={newProject}
      onDelete={remove}
    />
  );

  const canRerun =
    task && !streaming && ["planned", "done", "failed"].includes(task.status);

  return (
    <div className="mx-auto box-border w-full min-w-0 max-w-6xl px-4 pb-20 pt-4">
      <header className="mb-4 flex min-w-0 flex-wrap items-center justify-between gap-3">
        <span className="rounded-panel border border-line bg-panel px-3 py-1 text-xl font-bold">
          Flow.io
        </span>

        <div className="flex min-w-0 flex-wrap gap-2">
          <Link
            href="/tools"
            className="rounded-full border border-line bg-panel px-4 py-1.5 text-sm"
          >
            Tools
          </Link>

          <button
            onClick={async () => {
              await signOut();
              router.push("/");
            }}
            className="rounded-full border border-line bg-panel px-4 py-1.5 text-sm"
          >
            Sign out
          </button>
        </div>
      </header>

      {mode === "demo" && (
        <p
          role="note"
          className="mb-4 min-w-0 rounded-input border border-acc bg-panel p-2 text-sm"
        >
          Demo mode: tools are simulated, no keys are used, and every output is
          labelled Simulated.
        </p>
      )}

      <div className="grid min-w-0 grid-cols-1 gap-5 md:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="hidden min-w-0 md:block">{rail}</aside>

        <details className="min-w-0 rounded-input border border-line bg-panel p-3 md:hidden">
          <summary className="cursor-pointer text-sm font-semibold">
            Projects and history
          </summary>
          <div className="mt-3 min-w-0">{rail}</div>
        </details>

        <main className="flex min-w-0 w-full flex-col gap-4 max-md:flex-col-reverse">
          <div className="min-w-0 w-full max-md:sticky max-md:bottom-14 max-md:z-10">
            <Composer
              initial={prefill}
              busy={busy || streaming}
              token={token}
              onSubmit={run}
            />

            {problem && (
              <div
                role="alert"
                className="mt-3 min-w-0 rounded-input border border-bad bg-panel p-3 text-sm"
              >
                <p className="font-semibold text-bad">{problem.what}</p>
                <p>{problem.doing}</p>

                {problem.link && (
                  <Link
                    href={problem.link.href}
                    className="mt-1 inline-block underline"
                  >
                    {problem.link.text}
                  </Link>
                )}

                <details className="mt-1 min-w-0">
                  <summary className="cursor-pointer">View details</summary>
                  <p className="mt-1 whitespace-pre-wrap break-words text-mute">
                    {problem.details}
                  </p>
                </details>
              </div>
            )}
          </div>

          <div className="flex min-w-0 w-full flex-col gap-4">
            {task ? (
              <TaskCanvas key={task.id} task={task} transfers={transfers} />
            ) : (
              <div className="min-w-0 rounded-panel border border-line bg-panel p-5">
                <h2 className="text-xl font-bold">Your workspace is empty</h2>
                <p className="mt-1 text-mute">
                  Type an objective and press Run. Flow.io plans the steps,
                  picks a tool for each, and shows the work here.
                </p>
              </div>
            )}

            {notes.map((note) => (
              <p
                key={note}
                className="min-w-0 break-words rounded-input border border-line bg-panel p-2 text-sm"
              >
                Plan adjusted: {note}
              </p>
            ))}

            {streaming && live && (
              <div
                aria-live="polite"
                aria-label="Live output"
                className="fx-rise min-w-0 overflow-hidden rounded-input border border-acc bg-sunk p-3 text-sm"
              >
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-mute">
                  Writing…
                </p>
                <pre className="max-h-48 overflow-y-auto whitespace-pre-wrap break-words font-sans text-ink">
                  {live}
                  <span className="fx-caret" aria-hidden="true">▍</span>
                </pre>
              </div>
            )}

            {log.length > 0 && (
              <ul
                aria-live="polite"
                aria-label="Run activity"
                className="min-w-0 space-y-1 overflow-hidden rounded-input border border-line bg-panel p-3 text-sm"
              >
                {log.slice(-6).map((event) => (
                  <li
                    key={event.id}
                    className={`fx-rise break-words ${
                      event.type.endsWith("failed") ? "text-bad" : ""
                    }`}
                  >
                    {event.message}
                  </li>
                ))}
              </ul>
            )}

            {task?.status === "failed" && task.error && (
              <div
                role="alert"
                className="min-w-0 rounded-input border border-bad bg-panel p-3 text-sm"
              >
                <p className="font-semibold text-bad">{task.error.what}</p>
                <p>{task.error.doing}</p>

                <details className="mt-1 min-w-0">
                  <summary className="cursor-pointer">View details</summary>
                  <p className="mt-1 break-words text-mute">
                    {task.error.details}
                  </p>
                </details>
              </div>
            )}

            {canRerun && (
              <div className="min-w-0">
                <button
                  onClick={rerun}
                  disabled={busy}
                  className="rounded-action bg-acc px-4 py-2 text-sm font-semibold text-accink"
                >
                  {task!.status === "planned" ? "Run this plan" : "Run again"}
                </button>
              </div>
            )}

            {result && <ResultView r={result} />}

            {task && (streaming || ["done", "failed"].includes(task.status)) && (
              <FollowUpChat
                key={task.id}
                task={task}
                token={token}
                running={streaming}
                version={chatVersion}
                onSend={sendFollowUp}
              />
            )}
          </div>
        </main>
      </div>

      <StatusBar task={task} />
    </div>
  );
}
