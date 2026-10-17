"use client";

import Link from "next/link";
import { type AuditRecord, type Job, type Project, useApi } from "@/lib/api";
import { Badge, Card, CardHeader, Empty, ErrorNote, Stat, Table } from "@/components/ui/primitives";
import { shortTime } from "@/lib/utils";

export function Overview() {
  const projects = useApi<Project[]>("/projects");
  const audits = useApi<AuditRecord[]>("/audits?limit=20", 5000);
  const jobs = useApi<Job[]>("/jobs?limit=10", 3000);
  const recent = audits.data ?? [];
  const errors = recent.reduce((sum, a) => sum + a.errors, 0);
  const warnings = recent.reduce((sum, a) => sum + a.warnings, 0);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Agent network QA</h1>
        <p className="mt-1 text-sm text-muted">
          Lint topology, run scenarios with chaos, prove sly_data leaks and verify fixes — for every Neuro-SAN network.
        </p>
      </div>
      <ErrorNote error={projects.error ?? audits.error} />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Projects" value={projects.data?.length ?? "–"} />
        <Stat label="Recent audits" value={recent.length} />
        <Stat label="Errors (recent)" value={errors} tone={errors ? "error" : "ok"} />
        <Stat label="Warnings (recent)" value={warnings} tone={warnings ? "warning" : "ok"} />
      </div>
      <section className="space-y-4">
        <h2 className="text-sm font-semibold text-muted">Targets</h2>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {(projects.data ?? []).flatMap((project) =>
            project.targets.map((target) => (
              <Link key={`${project.name}/${target.name}`} href={`/projects/${project.name}/${target.name}`}>
                <Card className="h-full p-4 transition-colors hover:border-accent">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{target.name}</span>
                    <Badge>{project.name}</Badge>
                  </div>
                  <p className="mt-2 text-sm text-muted">{target.description || "No description."}</p>
                </Card>
              </Link>
            )),
          )}
        </div>
      </section>
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Recent audits" />
          {recent.length ? (
            <Table head={["Audit", "Target", "Errors", "Warnings", "Runs", "When"]}>
              {recent.map((audit) => (
                <tr key={audit.id} className="hover:bg-background">
                  <td className="px-4 py-2 font-mono text-xs">
                    <Link className="text-accent hover:underline" href={`/audits/${audit.id}`}>
                      {audit.id}
                    </Link>
                  </td>
                  <td className="px-4 py-2">{audit.target}</td>
                  <td className="px-4 py-2">{audit.errors ? <Badge tone="error">{audit.errors}</Badge> : <Badge tone="ok">0</Badge>}</td>
                  <td className="px-4 py-2">{audit.warnings ? <Badge tone="warning">{audit.warnings}</Badge> : "0"}</td>
                  <td className="px-4 py-2 tabular-nums">{audit.runs}</td>
                  <td className="px-4 py-2 text-xs text-muted">{shortTime(audit.created_at)}</td>
                </tr>
              ))}
            </Table>
          ) : (
            <Empty>No audits yet — open a target and run one.</Empty>
          )}
        </Card>
        <Card>
          <CardHeader title="Jobs" />
          <ul className="divide-y divide-border text-sm">
            {(jobs.data ?? []).map((job) => (
              <li key={job.id} className="flex items-center justify-between gap-2 px-5 py-2">
                <span>
                  <span className="font-medium">{job.kind}</span>{" "}
                  <span className="text-xs text-muted">{String(job.params.project ?? "")}</span>
                </span>
                <Badge tone={job.status === "succeeded" ? "ok" : job.status === "failed" ? "error" : "info"}>{job.status}</Badge>
              </li>
            ))}
            {jobs.data?.length ? null : <Empty>No jobs.</Empty>}
          </ul>
        </Card>
      </div>
    </div>
  );
}
