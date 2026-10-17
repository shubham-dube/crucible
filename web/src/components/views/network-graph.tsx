"use client";

import { Background, Controls, type Edge, MarkerType, type Node, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";
import type { Graph } from "@/lib/api";

const KIND_COLOR: Record<string, string> = {
  llm_agent: "var(--info)",
  coded_tool: "var(--accent)",
  toolbox: "var(--warning)",
  external: "var(--muted)",
  mcp: "var(--ok)",
};

/** Layered layout: depth from the front man (BFS) on the y axis, siblings spread on x. */
function layout(graph: Graph): { nodes: Node[]; edges: Edge[] } {
  const depth = new Map<string, number>();
  if (graph.front_man) {
    depth.set(graph.front_man, 0);
    const queue = [graph.front_man];
    while (queue.length) {
      const current = queue.shift() as string;
      for (const edge of graph.edges.filter((e) => e.source === current)) {
        if (!depth.has(edge.target)) {
          depth.set(edge.target, (depth.get(current) ?? 0) + 1);
          queue.push(edge.target);
        }
      }
    }
  }
  const maxDepth = Math.max(0, ...depth.values());
  const rows = new Map<number, string[]>();
  for (const node of graph.nodes) {
    const d = depth.get(node.id) ?? maxDepth + 1;
    rows.set(d, [...(rows.get(d) ?? []), node.id]);
  }
  const nodes: Node[] = graph.nodes.map((node) => {
    const d = depth.get(node.id) ?? maxDepth + 1;
    const row = rows.get(d) ?? [];
    const index = row.indexOf(node.id);
    return {
      id: node.id,
      position: { x: (index - (row.length - 1) / 2) * 220, y: d * 130 },
      data: { label: node.id },
      style: {
        border: `2px solid ${KIND_COLOR[node.kind] ?? "var(--border)"}`,
        background: "var(--surface)",
        color: "var(--foreground)",
        borderRadius: 8,
        fontSize: 12,
        width: 180,
        fontWeight: node.id === graph.front_man ? 700 : 400,
      },
    };
  });
  const bidirectional = new Set(
    graph.edges.filter((e) => graph.edges.some((o) => o.source === e.target && o.target === e.source)).map((e) => `${e.source}>${e.target}`),
  );
  const edges: Edge[] = graph.edges.map((edge) => {
    const loop = bidirectional.has(`${edge.source}>${edge.target}`);
    return {
      id: `${edge.source}>${edge.target}`,
      source: edge.source,
      target: edge.target,
      animated: loop,
      markerEnd: { type: MarkerType.ArrowClosed },
      style: { stroke: loop ? "var(--error)" : "var(--muted)" },
      label: loop ? "cycle" : undefined,
    };
  });
  return { nodes, edges };
}

export function NetworkGraph({ graph }: { graph: Graph }) {
  const { nodes, edges } = useMemo(() => layout(graph), [graph]);
  return (
    <div className="h-[420px] w-full">
      <ReactFlow nodes={nodes} edges={edges} fitView proOptions={{ hideAttribution: true }} nodesConnectable={false}>
        <Background gap={16} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

export const KIND_LEGEND = Object.entries(KIND_COLOR);
