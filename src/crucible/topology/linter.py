"""Run all lint rules (and Neuro-SAN's validators) over a loaded network."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from crucible.domain.findings import Finding, Severity, dedupe_findings, sort_findings
from crucible.integrations.neurosan.loader import LoadedNetwork
from crucible.integrations.neurosan.validators import RULE_ID as NEUROSAN_RULE_ID
from crucible.integrations.neurosan.validators import run_neurosan_validators
from crucible.topology.rules import LintConfig, RuleRegistry, registry


class LintResult(BaseModel):
    """Findings for one network plus summary counts."""

    model_config = ConfigDict(frozen=True)

    network: str
    file: str | None
    findings: tuple[Finding, ...]

    def count(self, severity: Severity) -> int:
        """Number of findings with exactly this severity."""
        return sum(1 for f in self.findings if f.severity is severity)

    def fails(self, threshold: Severity | None) -> bool:
        """True when any finding is at least as severe as ``threshold`` (None never fails)."""
        if threshold is None:
            return False
        return any(f.severity.rank >= threshold.rank for f in self.findings)


def lint(loaded: LoadedNetwork, config: LintConfig | None = None, rules: RuleRegistry | None = None) -> LintResult:
    """Lint a network: every enabled rule plus (optionally) Neuro-SAN's own validators."""
    cfg = config or LintConfig()
    reg = rules or registry
    graph = loaded.graph
    findings: list[Finding] = []
    for lint_rule in reg.rules():
        if lint_rule.id not in cfg.disabled:
            findings.extend(lint_rule.check(graph, cfg))
    if cfg.run_neurosan_validators and NEUROSAN_RULE_ID not in cfg.disabled:
        active = frozenset(r.id for r in reg.rules() if r.id not in cfg.disabled)
        findings.extend(run_neurosan_validators(loaded.raw_config, graph.name, graph.source_path, skip_rules=active))
    return LintResult(
        network=graph.name, file=graph.source_path, findings=tuple(sort_findings(dedupe_findings(findings)))
    )
