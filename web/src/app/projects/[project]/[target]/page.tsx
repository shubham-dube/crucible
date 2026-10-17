import { Suspense } from "react";
import { TargetView } from "@/components/views/target-view";

export default function TargetPage({ params }: PageProps<"/projects/[project]/[target]">) {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
      <TargetView params={params} />
    </Suspense>
  );
}
