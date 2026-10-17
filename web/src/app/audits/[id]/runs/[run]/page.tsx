import { Suspense } from "react";
import { RunView } from "@/components/views/run-view";

export default function RunPage({ params }: PageProps<"/audits/[id]/runs/[run]">) {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
      <RunView params={params} />
    </Suspense>
  );
}
