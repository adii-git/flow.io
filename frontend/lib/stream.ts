"use client";
import { useEffect, useRef } from "react";
import type { TaskEvent } from "./types";

/** Reads the task's server-sent events with fetch, so the bearer token can travel in a header. */
export function useTaskStream(taskId: string | null, token: string | null, onEvent: (e: TaskEvent) => void, onEnd: () => void) {
  const cb = useRef({ onEvent, onEnd });
  cb.current = { onEvent, onEnd };
  useEffect(() => {
    if (!taskId || !token) return;
    const ac = new AbortController();
    (async () => {
      try {
        const res = await fetch(`/api/tasks/${taskId}/stream`, { headers: { Authorization: `Bearer ${token}` }, signal: ac.signal, credentials: "include" });
        if (!res.ok || !res.body) return;
        const reader = res.body.getReader(), dec = new TextDecoder();
        let buf = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          let i;
          while ((i = buf.indexOf("\n\n")) >= 0) {
            const raw = buf.slice(0, i); buf = buf.slice(i + 2);
            const id = /^id: (\d+)/m.exec(raw)?.[1], data = /^data: (.*)$/m.exec(raw)?.[1];
            if (data) cb.current.onEvent({ ...JSON.parse(data), id: Number(id) });
          }
        }
      } catch { /* aborted or dropped: onEnd refetches the truth */ }
      if (!ac.signal.aborted) cb.current.onEnd();
    })();
    return () => ac.abort();
  }, [taskId, token]);
}
