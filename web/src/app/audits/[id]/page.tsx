import { Suspense } from "react";
import { AuditView } from "@/components/views/audit-view";

export default function AuditPage({ params }: PageProps<"/audits/[id]">) {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
      <AuditView params={params} />
    </Suspense>
  );
}
