"use client";

import Link from "next/link";
import { use, useState } from "react";
import { type RunDetail, useApi } from "@/lib/api";
import { Badge, Card, CardHeader, ErrorNote } from "@/components/ui/primitives";

const KIND_TONE: Record<string, "error" | "warning" | "info" | "ok" | "neutral"> = {
  delegation: "info",
  tool_error: "error",
  tool_result: "ok",
  tool_return: "neutral",
  llm_output: "warning",
  final_answer: "ok",
};
const HIDDEN = new Set(["tokens", "framework"]);

export function RunView({ params }: { params: Promise<{ id: string; run: string }> }) {
  const { id, run } = use(params);
  const runId = decodeURIComponent(run);
  const detail = useApi<RunDetail>(`/audits/${id}/runs/${encodeURIComponent(runId)}`);
  const [showAll, setShowAll] = useState(false);
  const data = detail.data;
  const spans = (data?.spans ?? []).filter((s) => showAll || !HIDDEN.has(s.kind));

  return (
    <div className="space-y-6">
      <div>
        <div className="text-xs text-muted">
          <Link href={`/audits/${id}`} className="hover:underline">
            audit
          </Link>{" "}
          / run
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">{data?.scenario_id ?? "…"}</h1>
        <p className="font-mono text-xs text-muted">{runId}</p>
      </div>
      <ErrorNote error={detail.error} />
      {data?.chaos_fired.length ? (
        <div className="rounded-md border border-warning/40 bg-warning/10 px-4 py-2 text-sm">
          Chaos fired: <span className="font-mono text-xs">{data.chaos_fired.join(" · ")}</span>
        </div>
      ) : null}
      <Card>
        <CardHeader
          title="Trace"
          subtitle={`${data?.spans.length ?? 0} spans · ${data?.tokens.total ?? 0} tokens · ${data?.duration_s ?? 0}s`}
          action={
            <label className="flex items-center gap-2 text-xs text-muted">
              <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} /> show token/framework spans
            </label>
          }
        />
        <ol className="divide-y divide-border">
          {spans.map((span) => (
            <li key={span.id} className="grid grid-cols-[4rem_8rem_10rem_1fr] gap-3 px-5 py-2 text-sm">
              <span className="font-mono text-xs text-muted">{span.t.toFixed(2)}s</span>
              <span>
                <Badge tone={KIND_TONE[span.kind] ?? "neutral"}>{span.kind}</Badge>
              </span>
              <span className="truncate font-medium">
                {span.agent ?? "-"}
                {span.target ? <span className="text-muted"> → {span.target}</span> : null}
              </span>
              <span className="whitespace-pre-wrap break-words font-mono text-xs">
                {span.kind === "delegation" ? JSON.stringify(span.data.params ?? {}) : span.text.slice(0, 600)}
              </span>
            </li>
          ))}
        </ol>
      </Card>
      <Card>
        <CardHeader title="Exact LLM inputs" subtitle="Captured per model call; tracked secrets are redacted." />
        <div className="divide-y divide-border">
          {(data?.llm_calls ?? []).map((call) => (
            <details key={call.id} className="px-5 py-2 text-sm">
              <summary className="cursor-pointer">
                <span className="font-mono text-xs">{call.id}</span> <span className="text-muted">@ {call.agent ?? "?"}</span>
              </summary>
              <div className="mt-2 space-y-2">
                {call.messages.map((message, i) => (
                  <div key={i} className="rounded bg-background p-2 font-mono text-xs">
                    <span className="text-muted">{message.role}: </span>
                    <span className="whitespace-pre-wrap">{message.content}</span>
                  </div>
                ))}
              </div>
            </details>
          ))}
        </div>
      </Card>
    </div>
  );
}
