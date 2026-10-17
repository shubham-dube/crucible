"""Safety rules: budgets and sly_data exposure."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from crucible.domain.findings import Finding, Severity
from crucible.domain.network import NetworkGraph
from crucible.topology.rules.base import LintConfig, make_finding, rule

_NEUROSAN_DEFAULT_MAX_STEPS = 10_000


@rule
class UnboundedBudget:
    """Without explicit limits a looping network burns tokens until the framework default (10k steps)."""

    id = "topology/unbounded-budget"
    severity = Severity.WARNING
    summary = "Network declares no execution time limit or keeps the default step budget"

    def check(self, graph: NetworkGraph, config: LintConfig) -> Iterable[Finding]:
        limits = graph.limits
        if limits.max_execution_seconds is None:
            yield make_finding(
                self,
                graph,
                "No max_execution_seconds set; a looping run is only stopped by the step budget.",
                remediation="Set max_execution_seconds at the top level of the network.",
                json_path="max_execution_seconds",
            )
        if limits.max_steps is None or limits.max_steps >= _NEUROSAN_DEFAULT_MAX_STEPS:
            yield make_finding(
                self,
                graph,
                f"max_steps is {limits.max_steps or 'unset (default 10000)'}; loops can run for a very long time.",
                remediation="Set max_steps to a realistic bound for this network (e.g. 50-200).",
                json_path="max_steps",
                severity=Severity.INFO if limits.max_execution_seconds is not None else Severity.WARNING,
            )


def _is_wildcard(value: Any) -> bool:
    if value is True or value == "*":
        return True
    if isinstance(value, list):
        return "*" in value
    if isinstance(value, dict):
        return value.get("*") is True
    return False


@rule
class SlyDataPassthrough:
    """sly_data allow-lists should name keys; wildcards forward every secret across the boundary."""

    id = "topology/sly-data-passthrough"
    severity = Severity.WARNING
    summary = "sly_data is forwarded wholesale instead of by explicit keys"

    _DIRECTIONS = ("to_downstream", "from_downstream", "to_upstream", "to_tracing")

    def check(self, graph: NetworkGraph, config: LintConfig) -> Iterable[Finding]:
        for name, node in graph.nodes.items():
            for direction in self._DIRECTIONS:
                block = node.allow.get(direction)
                if isinstance(block, dict) and _is_wildcard(block.get("sly_data")):
                    yield make_finding(
                        self,
                        graph,
                        f"Agent '{name}' allows ALL sly_data {direction.replace('_', ' ')}.",
                        agent=name,
                        severity=Severity.ERROR if direction == "to_tracing" else Severity.WARNING,
                        remediation=f'List only the keys that must cross: allow.{direction}.sly_data = ["key"].',
                    )
