"""Lint rule port and registry."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from crucible.domain.findings import Finding, Location, Severity
from crucible.domain.network import NetworkGraph


class LintConfig(BaseModel):
    """User-tunable lint behaviour."""

    model_config = ConfigDict(frozen=True)

    disabled: frozenset[str] = frozenset()
    max_depth: int = 4
    max_fan_out: int = 8
    routing_overlap_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    min_description_chars: int = 20
    run_neurosan_validators: bool = True


@runtime_checkable
class LintRule(Protocol):
    """A static check over a ``NetworkGraph``."""

    id: str
    severity: Severity
    summary: str

    def check(self, graph: NetworkGraph, config: LintConfig) -> Iterable[Finding]:
        """Yield findings for ``graph``."""
        ...


class RuleRegistry:
    """Holds lint rules by id. Third-party rules register through ``register``."""

    def __init__(self) -> None:
        self._rules: dict[str, LintRule] = {}

    def register(self, rule: LintRule) -> LintRule:
        """Add a rule instance; ids must be unique."""
        if rule.id in self._rules:
            raise ValueError(f"duplicate lint rule id: {rule.id}")
        self._rules[rule.id] = rule
        return rule

    def rules(self) -> list[LintRule]:
        """All registered rules sorted by id."""
        return [self._rules[k] for k in sorted(self._rules)]

    def get(self, rule_id: str) -> LintRule:
        """Look up a rule by id."""
        return self._rules[rule_id]


registry = RuleRegistry()


def rule[T](cls: type[T]) -> type[T]:
    """Class decorator: instantiate and register a rule in the default registry."""
    instance: Any = cls()
    registry.register(instance)
    return cls


def make_finding(
    rule_obj: LintRule,
    graph: NetworkGraph,
    message: str,
    agent: str | None = None,
    remediation: str | None = None,
    severity: Severity | None = None,
    json_path: str | None = None,
) -> Finding:
    """Build a finding with the graph's file and the agent's tools-list position as location."""
    node = graph.nodes.get(agent) if agent else None
    path = json_path or (f"tools[{node.index}]" if node is not None and node.index >= 0 else None)
    return Finding(
        rule_id=rule_obj.id,
        severity=severity or rule_obj.severity,
        message=message,
        agent=agent,
        location=Location(file=graph.source_path, agent=agent, json_path=path),
        remediation=remediation,
    )


CheckFn = Callable[[NetworkGraph, LintConfig], Iterable[Finding]]
