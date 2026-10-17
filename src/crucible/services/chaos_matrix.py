"""Chaos matrix: run a target's scenarios under baseline and each fault profile, report what each fault breaks."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from crucible.config.project import TargetSpec
from crucible.domain.chaos import FaultKind, FaultSpec
from crucible.domain.findings import Finding, Severity
from crucible.domain.network import AgentKind
from crucible.integrations.neurosan.loader import load_network
from crucible.services.audit import AuditOptions, AuditService

DEFAULT_KINDS = (FaultKind.EXCEPTION, FaultKind.EMPTY, FaultKind.MALFORMED, FaultKind.INJECTED_INSTRUCTION)


class ProfileResult(BaseModel):
    """Findings under one chaos profile, and which are new versus the baseline."""

    model_config = ConfigDict(frozen=True)

    profile: str
    findings: tuple[Finding, ...]
    new_findings: tuple[Finding, ...]

    @property
    def resilient(self) -> bool:
        """No new warning-or-worse findings compared to the baseline."""
        return not any(f.severity.rank >= Severity.WARNING.rank for f in self.new_findings)


class ChaosMatrix(BaseModel):
    """All profiles for one target."""

    model_config = ConfigDict(frozen=True)

    target: str
    baseline: tuple[Finding, ...]
    profiles: tuple[ProfileResult, ...]

    @property
    def resilience(self) -> float:
        """Share of fault profiles that introduced no new defects."""
        return sum(p.resilient for p in self.profiles) / len(self.profiles) if self.profiles else 1.0

    def to_markdown(self) -> str:
        """Matrix as a markdown table."""
        lines = [
            f"## Chaos matrix — {self.target}",
            "",
            f"Resilience: **{self.resilience:.0%}** of fault profiles introduced no new defects.",
            "",
            "| profile | resilient | new findings |",
            "|---|---|---|",
        ]
        for p in self.profiles:
            new = ", ".join(sorted({f"{f.rule_id}@{f.agent or '*'}" for f in p.new_findings})) or "-"
            lines.append(f"| `{p.profile}` | {'yes' if p.resilient else 'NO'} | {new} |")
        return "\n".join(lines) + "\n"


def default_profiles(service: AuditService, spec: TargetSpec, kinds: Sequence[FaultKind] = DEFAULT_KINDS) -> list[str]:
    """One profile per fault kind x coded tool of the target."""
    graph = load_network(service.project.network_path(spec)).graph
    tools = sorted(n.name for n in graph.nodes.values() if n.kind is AgentKind.CODED_TOOL)
    return [FaultSpec(kind=kind, target=tool).id for tool in tools for kind in kinds]


def run_matrix(
    service: AuditService,
    spec: TargetSpec,
    profiles: Sequence[str] | None = None,
    options: AuditOptions | None = None,
) -> ChaosMatrix:
    """Baseline audit plus one audit per profile; static findings are excluded (they do not change)."""
    base_opts = options or AuditOptions()
    baseline = service.audit_target(spec, base_opts.model_copy(update={"chaos": ()})).runtime_findings
    seen = {f.fingerprint for f in baseline}
    results = []
    for profile in profiles if profiles is not None else default_profiles(service, spec):
        audit = service.audit_target(spec, base_opts.model_copy(update={"chaos": (profile,)}))
        new = tuple(f for f in audit.runtime_findings if f.fingerprint not in seen)
        results.append(ProfileResult(profile=profile, findings=audit.runtime_findings, new_findings=new))
    return ChaosMatrix(target=spec.name, baseline=baseline, profiles=tuple(results))
