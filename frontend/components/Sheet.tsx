"use client";
import { useEffect, useRef, type ReactNode } from "react";

/** Bottom sheet on phones, side panel on larger screens. */
export default function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.focus();
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    addEventListener("keydown", k); return () => removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-30">
      <button aria-label="Close details" onClick={onClose} className="fx-backdrop absolute inset-0 bg-ink/40" />
      <div ref={ref} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1}
        className="fx-sheet absolute inset-x-0 bottom-0 max-h-[80vh] overflow-y-auto rounded-t-2xl border border-line bg-panel p-5 md:inset-y-0 md:left-auto md:right-0 md:max-h-none md:w-[440px] md:rounded-none"
        style={{ paddingBottom: "max(1.25rem, env(safe-area-inset-bottom))" }}>
        <div className="mb-3 flex items-start justify-between gap-3">
          <h2 className="text-xl font-bold tracking-tight">{title}</h2>
          <button onClick={onClose} className="rounded-full border border-line bg-sunk px-3 py-1 text-sm">Close</button>
        </div>
        {children}
      </div>
    </div>
  );
}
