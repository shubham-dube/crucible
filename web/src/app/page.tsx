import { Suspense } from "react";
import { Overview } from "@/components/views/overview";

export default function Home() {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
      <Overview />
    </Suspense>
  );
}
