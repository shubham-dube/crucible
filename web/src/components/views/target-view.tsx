"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useCallback, useState } from "react";
import { type Graph, type Job, type Finding, request, useApi } from "@/lib/api";
import { Badge, Button, Card, CardHeader, ErrorNote } from "@/components/ui/primitives";
import { FindingsTable } from "./findings-table";
import { JobProgress } from "./job-progress";
import { KIND_LEGEND, NetworkGraph } from "./network-graph";

const FAULTS = ["exception", "empty", "malformed", "injected-instruction", "latency"] as const;

export function TargetView({ params }: { params: Promise<{ project: string; target: string }> }) {
  const { project, target } = use(params);
  const router = useRouter();
  const graph = useApi<Graph>(`/projects/${project}/targets/${target}/graph`);
  const lint = useApi<{ findings: Finding[] }>(`/projects/${project}/targets/${target}/lint`);
  const [repetitions, setRepetitions] = useState(1);
  const [chaos, setChaos] = useState<string[]>([]);
  const [agentic, setAgentic] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const tools = (graph.data?.nodes ?? []).filter((n) => n.kind === "coded_tool").map((n) => n.id);

  async function start() {
    setError(null);
    try {
      const job = await request<Job>("/audits", {
        method: "POST",
        body: JSON.stringify({ project, targets: [target], repetitions, chaos, agentic, scripted: agentic }),
      });
      setJobId(job.id);
    } catch (e) {
      setError(e);
    }
  }

  const onDone = useCallback(
    (job: Job) => {
      const ids = (job.result.audit_ids ?? {}) as Record<string, string>;
      const auditId = ids[target] ?? ((job.result.audit_ids as string[] | undefined) ?? [])[0];
      if (auditId) router.push(`/audits/${auditId}`);
    },
    [router, target],
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-xs text-muted">
            <Link href="/" className="hover:underline">
              Overview
            </Link>{" "}
            / {project}
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">{target}</h1>
        </div>
      </div>
      <ErrorNote error={graph.error ?? lint.error ?? error} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Delegation graph"
            subtitle="Red animated edges are delegation cycles (ping-pong risk)."
            action={
              <div className="flex flex-wrap gap-2 text-xs">
                {KIND_LEGEND.map(([kind, color]) => (
                  <span key={kind} className="flex items-center gap-1 text-muted">
                    <span className="inline-block h-2 w-2 rounded-full" style={{ background: color }} />
                    {kind.replace("_", " ")}
                  </span>
                ))}
              </div>
            }
          />
          {graph.data ? <NetworkGraph graph={graph.data} /> : <div className="h-[420px]" />}
        </Card>
        <Card>
          <CardHeader title="Run an audit" subtitle="Lint + execute scenarios + judge traces." />
          <div className="space-y-4 p-5 text-sm">
            <label className="flex items-center justify-between gap-3">
              Repetitions per scenario
              <input
                type="number"
                min={1}
                max={20}
                value={repetitions}
                onChange={(e) => setRepetitions(Number(e.target.value) || 1)}
                className="w-20 rounded-md border border-border bg-background px-2 py-1"
              />
            </label>
            <fieldset className="space-y-2">
              <legend className="mb-1 text-xs font-medium text-muted">Chaos faults (coded tools)</legend>
              {tools.length === 0 ? <p className="text-xs text-muted">No coded tools.</p> : null}
              {tools.flatMap((tool) =>
                FAULTS.map((fault) => {
                  const id = `${fault}:${tool}`;
                  return (
                    <label key={id} className="flex items-center gap-2 text-xs">
                      <input
                        type="checkbox"
                        checked={chaos.includes(id)}
                        disabled={agentic}
                        onChange={(e) => setChaos(e.target.checked ? [...chaos, id] : chaos.filter((c) => c !== id))}
                      />
                      <span className="font-mono">{id}</span>
                    </label>
                  );
                }),
              )}
            </fieldset>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={agentic} onChange={(e) => setAgentic(e.target.checked)} />
              Agentic audit (Crucible&apos;s own agent network plans it)
            </label>
            <Button onClick={start} disabled={jobId !== null && !graph.data} className="w-full">
              Run audit
            </Button>
            {jobId ? <JobProgress jobId={jobId} onDone={onDone} /> : null}
          </div>
        </Card>
      </div>
      <Card>
        <CardHeader
          title="Static lint"
          action={<Badge tone={lint.data?.findings.some((f) => f.severity === "error") ? "error" : "ok"}>{lint.data?.findings.length ?? 0} findings</Badge>}
        />
        <FindingsTable findings={lint.data?.findings ?? []} />
      </Card>
    </div>
  );
}
