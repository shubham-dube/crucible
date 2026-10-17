"""Fix loop: propose fixes for an audit's findings and keep only those the verifier accepts."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from crucible.config.project import TargetSpec
from crucible.domain.audit import TargetAudit
from crucible.domain.findings import Severity
from crucible.domain.fix import FixProposal, FixVerdict
from crucible.domain.scenario import Scenario
from crucible.fixes.proposers import propose
from crucible.fixes.verify import verify
from crucible.integrations.neurosan.loader import build_graph, load_config
from crucible.services.audit import AuditOptions, AuditService


def proposals_for(service: AuditService, spec: TargetSpec, audit: TargetAudit) -> list[FixProposal]:
    """Candidate fixes for warning-or-worse findings of an audit."""
    path = service.project.network_path(spec)
    config = load_config(path)
    graph = build_graph(config, path.stem, str(path))
    significant = [f for f in audit.findings if f.severity.rank >= Severity.WARNING.rank]
    return propose(significant, graph, config)


def fix_target(
    service: AuditService,
    spec: TargetSpec,
    workdir: Path,
    scenarios: Sequence[Scenario] | None = None,
    options: AuditOptions | None = None,
    baseline: TargetAudit | None = None,
) -> tuple[TargetAudit, list[FixVerdict]]:
    """Audit (unless given), propose, verify each proposal independently."""
    suite = list(scenarios) if scenarios is not None else list(service.project.scenarios(spec).scenarios)
    audit = baseline or service.audit_target(spec, options, scenarios=suite)
    verdicts = [
        verify(service, spec, audit, proposal, suite, workdir, options)
        for proposal in proposals_for(service, spec, audit)
    ]
    return audit, verdicts
