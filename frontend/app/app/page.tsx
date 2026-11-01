import { Suspense } from "react";
import Workspace from "@/components/Workspace";

export default function Page() {
  return <Suspense fallback={<main className="p-6 text-mute">Loading your workspace</main>}><Workspace /></Suspense>;
}
