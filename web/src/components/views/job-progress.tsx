"use client";

import { useEffect, useState } from "react";
import { API, type Job, request } from "@/lib/api";
import { Badge } from "@/components/ui/primitives";

type JobEvent = Record<string, unknown> & { type: string };

/** Streams a job's server-sent events and reports the final job record. */
export function JobProgress({ jobId, onDone }: { jobId: string; onDone?: (job: Job) => void }) {
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [status, setStatus] = useState<string>("queued");

  useEffect(() => {
    const source = new EventSource(`${API}/jobs/${jobId}/events`);
    source.onmessage = (message) => {
      const event = JSON.parse(message.data) as JobEvent;
      setEvents((previous) => [...previous, event]);
      if (event.type === "started") setStatus("running");
    };
    source.addEventListener("end", () => {
      source.close();
      void request<Job>(`/jobs/${jobId}`).then((job) => {
        setStatus(job.status);
        onDone?.(job);
      });
    });
    source.onerror = () => source.close();
    return () => source.close();
  }, [jobId, onDone]);

  const tone = status === "succeeded" ? "ok" : status === "failed" ? "error" : "info";
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-sm">
        <span className="font-mono text-xs text-muted">{jobId}</span>
        <Badge tone={tone}>{status}</Badge>
      </div>
      <ol className="max-h-56 space-y-1 overflow-y-auto rounded-md bg-background p-3 font-mono text-xs">
        {events.map((event, index) => (
          <li key={index} className="text-muted">
            <span className="text-foreground">{event.type}</span> {describe(event)}
          </li>
        ))}
      </ol>
    </div>
  );
}

function describe(event: JobEvent): string {
  if (event.type === "run") {
    return `${event.target}/${event.scenario}#${event.repetition} ${event.status} · ${event.delegations} hand-offs · ${event.duration_s}s`;
  }
  if (event.type === "handoff") return String(event.edge);
  if (event.type === "verdict") return `${event.proposal} ${event.accepted ? "ACCEPTED" : "rejected"}`;
  if (event.type === "error") return String(event.message);
  return "";
}
