"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

/**
 * Two global touches:
 * 1. A thin top bar that starts the moment an internal link is clicked and finishes exactly
 *    when the new route renders (pathname change), so the user always knows a switch is happening.
 * 2. A ripple on every button / link press, for clear click feedback.
 */
export default function RouteProgress() {
  const path = usePathname();
  const [state, setState] = useState<"idle" | "loading" | "done">("idle");
  const safety = useRef<ReturnType<typeof setTimeout> | null>(null);
  const first = useRef(true);

  // Route rendered: finish the bar.
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    if (safety.current) clearTimeout(safety.current);
    setState("done");
    const t = setTimeout(() => setState("idle"), 350);
    return () => clearTimeout(t);
  }, [path]);

  useEffect(() => {
    const start = () => {
      setState("loading");
      if (safety.current) clearTimeout(safety.current);
      safety.current = setTimeout(() => setState("idle"), 8000); // never leave a stuck bar
    };

    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as HTMLElement).closest("a");
      if (!a || a.target === "_blank" || a.hasAttribute("download")) return;
      const url = new URL(a.href, location.href);
      if (url.origin !== location.origin) return;
      if (url.pathname === location.pathname) return; // same page (or #hash): no route change
      start();
    };

    const ripple = (e: PointerEvent) => {
      const el = (e.target as HTMLElement).closest<HTMLElement>("button, a, summary");
      if (!el || (el as HTMLButtonElement).disabled) return;
      if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      const r = el.getBoundingClientRect();
      const size = Math.max(r.width, r.height) * 2;
      const dot = document.createElement("span");
      dot.className = "fx-ripple";
      dot.style.width = dot.style.height = `${size}px`;
      dot.style.left = `${e.clientX - r.left - size / 2}px`;
      dot.style.top = `${e.clientY - r.top - size / 2}px`;
      el.classList.add("fx-ripple-host");
      el.appendChild(dot);
      dot.addEventListener("animationend", () => dot.remove(), { once: true });
    };

    document.addEventListener("click", onClick, true);
    document.addEventListener("pointerdown", ripple);
    addEventListener("popstate", start);
    return () => {
      document.removeEventListener("click", onClick, true);
      document.removeEventListener("pointerdown", ripple);
      removeEventListener("popstate", start);
    };
  }, []);

  return <div aria-hidden="true" className={`fx-progress fx-progress-${state}`} />;
}
