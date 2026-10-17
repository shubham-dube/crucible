"use client";

import { useState } from "react";
import type { Finding } from "@/lib/api";
import { Badge, Empty, Table, severityTone } from "@/components/ui/primitives";

export function FindingsTable({ findings }: { findings: Finding[] }) {
  const [open, setOpen] = useState<number | null>(null);
  if (!findings.length) return <Empty>No findings.</Empty>;
  return (
    <Table head={["Severity", "Rule", "Agent", "Scenario", "Finding"]}>
      {findings.map((finding, index) => (
        <FindingRow key={index} finding={finding} open={open === index} onToggle={() => setOpen(open === index ? null : index)} />
      ))}
    </Table>
  );
}

function FindingRow({ finding, open, onToggle }: { finding: Finding; open: boolean; onToggle: () => void }) {
  return (
    <>
      <tr className="cursor-pointer align-top hover:bg-background" onClick={onToggle}>
        <td className="px-4 py-2">
          <Badge tone={severityTone(finding.severity)}>{finding.severity}</Badge>
        </td>
        <td className="px-4 py-2 font-mono text-xs">{finding.rule_id}</td>
        <td className="px-4 py-2">{finding.agent ?? "-"}</td>
        <td className="px-4 py-2 text-muted">{finding.scenario_id ?? "-"}</td>
        <td className="px-4 py-2">{finding.message}</td>
      </tr>
      {open ? (
        <tr className="bg-background">
          <td colSpan={5} className="space-y-3 px-4 py-3 text-sm">
            {finding.remediation ? (
              <p>
                <span className="font-medium">Fix: </span>
                {finding.remediation}
              </p>
            ) : null}
            {finding.evidence.length ? (
              <div>
                <div className="mb-1 text-xs font-medium text-muted">Evidence</div>
                <ul className="space-y-1 font-mono text-xs">
                  {finding.evidence.map((evidence, i) => (
                    <li key={i}>
                      <span className="text-muted">
                        {evidence.kind}:{evidence.ref}
                      </span>{" "}
                      {evidence.excerpt}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {finding.location.file ? (
              <p className="text-xs text-muted">
                {finding.location.file} {finding.location.json_path ? `· ${finding.location.json_path}` : ""}
              </p>
            ) : null}
          </td>
        </tr>
      ) : null}
    </>
  );
}
