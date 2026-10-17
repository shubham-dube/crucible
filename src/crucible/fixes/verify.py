"""Verify a fix by auditing a patched copy of the network with the same scenarios (the critic)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from crucible.config.project import TargetSpec
from crucible.domain.audit import TargetAudit
from crucible.domain.errors import ConfigError
from crucible.domain.findings import Severity
from crucible.domain.fix import FixProposal, FixVerdict
from crucible.domain.scenario import Scenario
from crucible.fixes.apply import apply_ops, config_diff, write_patched
from crucible.integrations.neurosan.loader import load_config
from crucible.services.audit import AuditOptions, AuditService


def verify(
    service: AuditService,
    spec: TargetSpec,
    baseline: TargetAudit,
    proposal: FixProposal,
    scenarios: Sequence[Scenario],
    workdir: Path,
    options: AuditOptions | None = None,
) -> FixVerdict:
    """Accept only if the target finding disappears and no new warning-or-worse finding appears."""
    if proposal.manual or not proposal.ops:
        return FixVerdict(proposal=proposal, accepted=False, target_fixed=False, reason="manual change required")
    original = service.project.network_path(spec)
    config = load_config(original)
    try:
        patched = apply_ops(config, proposal.ops)
    except ConfigError as exc:
        return FixVerdict(proposal=proposal, accepted=False, target_fixed=False, reason=f"invalid patch: {exc}")
    path = write_patched(patched, original.stem, workdir / proposal.id)
    audit = service.audit_target(spec, options, scenarios=list(scenarios), network_path=path)
    before = {f.fingerprint: f for f in baseline.findings}
    after = {f.fingerprint: f for f in audit.findings}
    target_fixed = proposal.finding_fingerprint not in after
    new = tuple(f for fp, f in after.items() if fp not in before and f.severity.rank >= Severity.WARNING.rank)
    resolved = tuple(f for fp, f in before.items() if fp not in after)
    accepted = target_fixed and not new
    if accepted:
        reason = f"verified: target finding gone, {len(resolved)} finding(s) resolved, no new findings"
    elif not target_fixed:
        reason = "target finding still present after the patch"
    else:
        reason = f"introduced {len(new)} new finding(s): " + ", ".join(sorted({f.rule_id for f in new}))
    return FixVerdict(
        proposal=proposal,
        accepted=accepted,
        target_fixed=target_fixed,
        resolved=resolved,
        new_findings=new,
        diff=config_diff(config, patched, original.name),
        patched_path=str(path),
        reason=reason,
    )
