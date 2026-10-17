"use client";

import Link from "next/link";
import { use, useState } from "react";
import { type AuditDetail, type DiffResult, type Job, type Project, request, useApi } from "@/lib/api";
import { Badge, Button, Card, CardHeader, Empty, ErrorNote, Stat, Table } from "@/components/ui/primitives";
import { FindingsTable } from "./findings-table";
import { JobProgress } from "./job-progress";

interface Verdict {
  proposal: { id: string; rule_id: string; agent: string | null; rationale: string; manual: boolean };
  accepted: boolean;
  reason: string;
  resolved: string[];
  diff: string;
}

export function AuditView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const audit = useApi<AuditDetail>(`/audits/${id}`);
  const diff = useApi<DiffResult>(`/audits/${id}/diff?against=main`);
  const projects = useApi<Project[]>("/projects");
  const [fixJob, setFixJob] = useState<string | null>(null);
  const [verdicts, setVerdicts] = useState<Verdict[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const data = audit.data;
  const errors = data?.findings.filter((f) => f.severity === "error").length ?? 0;
  const warnings = data?.findings.filter((f) => f.severity === "warning").length ?? 0;
  const project = projects.data?.find((p) => p.targets.some((t) => t.name === data?.target))?.name;

  async function findFixes(project: string) {
    setError(null);
    try {
      const job = await request<Job>(`/audits/${id}/fix`, { method: "POST", body: JSON.stringify({ project }) });
      setFixJob(job.id);
    } catch (e) {
      setError(e);
    }
  }

  async function setBaseline() {
    if (!data) return;
    try {
      await request(`/baselines/${data.target}/main?audit_id=${id}`, { method: "PUT" });
      await diff.mutate();
    } catch (e) {
      setError(e);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-xs text-muted">
            <Link href="/" className="hover:underline">
              Overview
            </Link>{" "}
            / audit
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">{data?.target ?? "…"}</h1>
          <p className="font-mono text-xs text-muted">{id}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={setBaseline} disabled={!data}>
            Set as baseline “main”
          </Button>
          <Button
            onClick={() => project && findFixes(project)}
            disabled={!data || !project || errors + warnings === 0 || fixJob !== null}
          >
            Find verified fixes
          </Button>
        </div>
      </div>
      <ErrorNote error={audit.error ?? error} />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Errors" value={errors} tone={errors ? "error" : "ok"} />
        <Stat label="Warnings" value={warnings} tone={warnings ? "warning" : "ok"} />
        <Stat label="Runs" value={data?.runs.length ?? "–"} />
        <Stat label="New vs main" value={diff.data ? diff.data.new.length : "–"} tone={diff.data?.new.length ? "error" : "ok"} />
      </div>
      <Card>
        <CardHeader title="Findings" subtitle="Click a row for evidence and the fix. Secrets are redacted." />
        <FindingsTable findings={data?.findings ?? []} />
      </Card>
      {fixJob || verdicts ? (
        <Card>
          <CardHeader title="Verified fixes" subtitle="Each proposal is applied to a copy of the network and re-audited." />
          <div className="space-y-4 p-5">
            {fixJob && !verdicts ? (
              <JobProgress jobId={fixJob} onDone={(job: Job) => setVerdicts((job.result.verdicts ?? []) as Verdict[])} />
            ) : null}
            {(verdicts ?? []).map((verdict) => (
              <div key={verdict.proposal.id} className="rounded-md border border-border">
                <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2 text-sm">
                  <Badge tone={verdict.accepted ? "ok" : verdict.proposal.manual ? "warning" : "error"}>
                    {verdict.accepted ? "ACCEPTED" : verdict.proposal.manual ? "MANUAL" : "REJECTED"}
                  </Badge>
                  <span className="font-mono text-xs">{verdict.proposal.rule_id}</span>
                  <span className="text-muted">@ {verdict.proposal.agent ?? "-"}</span>
                  <span className="ml-auto text-xs text-muted">{verdict.reason}</span>
                </div>
                <p className="px-4 py-2 text-sm">{verdict.proposal.rationale}</p>
                {verdict.diff ? (
                  <pre className="max-h-72 overflow-auto bg-background px-4 py-2 font-mono text-xs">
                    {verdict.diff.split("\n").map((line, i) => (
                      <div key={i} className={line.startsWith("+") ? "text-ok" : line.startsWith("-") ? "text-error" : "text-muted"}>
                        {line}
                      </div>
                    ))}
                  </pre>
                ) : null}
              </div>
            ))}
          </div>
        </Card>
      ) : null}
      <Card>
        <CardHeader title="Runs" />
        {data?.runs.length ? (
          <Table head={["Scenario", "Rep", "Status", "Hand-offs", "Tokens", "Seconds", "Chaos", "Answer"]}>
            {data.runs.map((run) => (
              <tr key={run.run_id} className="align-top hover:bg-background">
                <td className="px-4 py-2">
                  <Link className="text-accent hover:underline" href={`/audits/${id}/runs/${encodeURIComponent(run.run_id)}`}>
                    {run.scenario_id}
                  </Link>
                </td>
                <td className="px-4 py-2 tabular-nums">{run.repetition}</td>
                <td className="px-4 py-2">
                  <Badge tone={run.status === "ok" ? "ok" : "error"}>{run.status}</Badge>
                </td>
                <td className="px-4 py-2 tabular-nums">{run.delegations}</td>
                <td className="px-4 py-2 tabular-nums">{run.tokens}</td>
                <td className="px-4 py-2 tabular-nums">{run.duration_s.toFixed(1)}</td>
                <td className="px-4 py-2 font-mono text-xs">{run.chaos.join(", ") || "-"}</td>
                <td className="max-w-md px-4 py-2 text-muted">{run.answer}</td>
              </tr>
            ))}
          </Table>
        ) : (
          <Empty>No runs (static audit only).</Empty>
        )}
      </Card>
      {diff.data ? (
        <Card>
          <CardHeader title="Regression vs baseline “main”" subtitle={diff.data.baseline} />
          <div className="grid gap-4 p-5 text-sm md:grid-cols-3">
            <div>
              <div className="mb-1 text-xs font-medium text-muted">New ({diff.data.new.length})</div>
              {diff.data.new.map((f, i) => (
                <div key={i} className="font-mono text-xs text-error">{f.rule_id}</div>
              ))}
            </div>
            <div>
              <div className="mb-1 text-xs font-medium text-muted">Fixed ({diff.data.fixed.length})</div>
              {diff.data.fixed.map((f, i) => (
                <div key={i} className="font-mono text-xs text-ok">{f.rule_id}</div>
              ))}
            </div>
            <div>
              <div className="mb-1 text-xs font-medium text-muted">Unchanged</div>
              <div className="tabular-nums">{diff.data.persisting.length}</div>
            </div>
          </div>
        </Card>
      ) : null}
    </div>
  );
}
