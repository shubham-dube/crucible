// Typed client for the Crucible API (via the /api/crucible proxy). Types mirror web/openapi.json.
import useSWR, { type SWRResponse } from "swr";

export type Severity = "error" | "warning" | "info";

export interface Evidence {
  kind: string;
  ref: string;
  excerpt: string | null;
}

export interface Finding {
  rule_id: string;
  severity: Severity;
  message: string;
  agent: string | null;
  remediation: string | null;
  evidence: Evidence[];
  run_id: string | null;
  scenario_id: string | null;
  location: { file: string | null; agent: string | null; json_path: string | null };
}

export interface Project {
  name: string;
  targets: { name: string; description: string }[];
}

export interface GraphNode {
  id: string;
  kind: "llm_agent" | "coded_tool" | "toolbox" | "external" | "mcp";
  description: string;
  class: string | null;
}

export interface Graph {
  name: string;
  front_man: string | null;
  nodes: GraphNode[];
  edges: { source: string; target: string; kind: string }[];
  limits: Record<string, number | null>;
}

export interface AuditRecord {
  id: string;
  target: string;
  created_at: string;
  errors: number;
  warnings: number;
  runs: number;
}

export interface RunSummary {
  run_id: string;
  scenario_id: string;
  repetition: number;
  status: "ok" | "timeout" | "error";
  duration_s: number;
  tokens: number;
  delegations: number;
  chaos: string[];
  answer: string;
}

export interface AuditDetail {
  id: string;
  target: string;
  network_path: string;
  findings: Finding[];
  runs: RunSummary[];
}

export interface Span {
  id: string;
  seq: number;
  kind: string;
  agent: string | null;
  origin: string[];
  target: string | null;
  text: string;
  data: Record<string, unknown>;
  turn: number;
  t: number;
}

export interface RunDetail {
  run_id: string;
  scenario_id: string;
  status: string;
  answer: string;
  duration_s: number;
  spans: Span[];
  llm_calls: { id: string; agent: string | null; messages: { role: string; content: string }[] }[];
  chaos_fired: string[];
  tokens: { total: number };
}

export interface Job {
  id: string;
  kind: "audit" | "agentic" | "fix" | "bench";
  status: "queued" | "running" | "succeeded" | "failed";
  params: Record<string, unknown>;
  result: Record<string, unknown>;
  error: string | null;
  created_at: string;
}

export interface DiffResult {
  baseline: string;
  markdown: string;
  new: Finding[];
  fixed: Finding[];
  persisting: Finding[];
}

export const API = "/api/crucible";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = ((await response.json()) as { detail?: string }).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export function useApi<T>(path: string | null, refreshMs = 0): SWRResponse<T, ApiError> {
  return useSWR<T, ApiError>(path, (p: string) => request<T>(p), { refreshInterval: refreshMs });
}
