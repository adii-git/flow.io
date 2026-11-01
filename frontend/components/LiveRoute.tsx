"use client";

import { useEffect, useMemo, useRef } from "react";
import { createField, type Field } from "@/lib/field";
import type { Subtask } from "@/lib/types";

/** Animated workflow route constrained to its available container width. */
export default function LiveRoute({
  steps,
}: {
  steps: Subtask[];
}) {
  const cv = useRef<HTMLCanvasElement>(null);
  const fld = useRef<Field | null>(null);

  const active = useMemo(
    () =>
      steps.filter(
        (s) => s.routing?.tool_id && !s.routing.skipped,
      ),
    [steps],
  );

  const tools = useMemo(() => {
    const m = new Map<string, string>();

    active.forEach((s) => {
      m.set(
        s.routing!.tool_id!,
        s.routing!.tool_name ?? s.routing!.tool_id!,
      );
    });

    return Array.from(m);
  }, [active]);

  const key = tools.map(([id]) => id).join("|");

  useEffect(() => {
    const canvas = cv.current;
    if (!canvas) return;

    const mq = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    );

    const wells = tools.map(([id, label], i) => ({
      id,
      label,
      x:
        tools.length > 1
          ? 0.14 + (0.72 * i) / (tools.length - 1)
          : 0.5,
      y: i % 2 ? 0.7 : 0.32,
    }));

    const field = createField(canvas, {
      wells,
      reduced: mq.matches,
    });

    fld.current = field;

    const observer = new MutationObserver(() => {
      field.refreshColors();
    });

    observer.observe(document.documentElement, {
      attributes: true,
    });

    return () => {
      field.destroy();
      observer.disconnect();

      if (fld.current === field) {
        fld.current = null;
      }
    };
  }, [key]);

  useEffect(() => {
    const field = fld.current;
    if (!field) return;

    const route = active.map((s) => s.routing!.tool_id!);
    const current = active.findIndex(
      (s) => s.status === "running",
    );
    const done = active.filter(
      (s) => s.status === "done",
    ).length;

    field.setRoute(
      route,
      current >= 0
        ? current
        : Math.max(
            0,
            done - 1 + (done === active.length ? 0 : 1),
          ),
    );

    tools.forEach(([id]) => {
      const mine = active.filter(
        (s) => s.routing!.tool_id === id,
      );

      field.setTarget(
        id,
        mine.some((s) => s.status === "running")
          ? 1.9
          : mine.every((s) => s.status === "done")
            ? 0.9
            : 1.1,
      );
    });
  }, [active, tools]);

  if (tools.length < 1) return null;

  return (
    <div className="box-border w-full min-w-0 max-w-full overflow-hidden rounded-input">
      <canvas
        ref={cv}
        aria-hidden="true"
        className="block h-44 w-full min-w-0 max-w-full rounded-input border border-line bg-sunk"
      />
    </div>
  );
}
