import type { ReactNode } from "react";

/**
 * Next.js re-mounts a template on every route change (a layout does not), so this wrapper
 * replays the page-enter animation exactly once per navigation, and only then.
 */
export default function Template({ children }: { children: ReactNode }) {
  return <div className="fx-page">{children}</div>;
}
