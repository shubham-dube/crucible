"""Structural rules: graph shape, reachability and front-man validity."""

from __future__ import annotations

from collections.abc import Iterable

from crucible.domain.findings import Finding, Severity
from crucible.domain.network import AgentKind, EdgeKind, NetworkGraph
from crucible.topology.rules.base import LintConfig, make_finding, rule


def _cycles(graph: NetworkGraph) -> list[list[str]]:
    """Elementary cycles among internal agents (Johnson's algorithm via networkx)."""
    import networkx as nx

    g = nx.DiGraph()
    g.add_edges_from((e.src, e.dst) for e in graph.edges if e.kind is EdgeKind.INTERNAL and e.dst in graph.nodes)
    return [list(c) for c in nx.simple_cycles(g)]


@rule
class CycleRisk:
    """Cycles are legal in Neuro-SAN but let agents ping-pong a task until the step budget runs out."""

    id = "topology/cycle-risk"
    severity = Severity.WARNING
    summary = "Delegation cycle can cause ping-pong loops"

    def check(self, graph: NetworkGraph, config: LintConfig) -> Iterable[Finding]:
        for cycle in _cycles(graph):
            path = " -> ".join([*cycle, cycle[0]])
            yield make_finding(
                self,
                graph,
                f"Delegation cycle {path}; agents can bounce work back and forth.",
                agent=cycle[0],
                remediation="Break the cycle, or instruct agents explicitly when NOT to call back; cap max_steps.",
            )


@rule
class UnreachableAgent:
    """Agents the front man can never reach are dead config or a wiring mistake."""

    id = "topology/unreachable-agent"
    severity = Severity.WARNING
    summary = "Agent is not reachable from the front man"

    def check(self, graph: NetworkGraph, config: LintConfig) -> Iterable[Finding]:
        reachable = graph.reachable_from(graph.front_man)
        for name, node in graph.nodes.items():
            if node.index >= 0 and name not in reachable:
                yield make_finding(
                    self,
                    graph,
                    f"Agent '{name}' is not reachable from front man '{graph.front_man}'.",
                    agent=name,
                    remediation="Add it to a parent's 'tools' list or delete it.",
                )


@rule
class MaxDepth:
    """Deep delegation chains multiply latency, cost and error compounding."""

    id = "topology/max-depth"
    severity = Severity.WARNING
    summary = "Delegation chain is deeper than the configured maximum"

    def check(self, graph: NetworkGraph, config: LintConfig) -> Iterable[Finding]:
        for name, depth in sorted(graph.depths().items()):
            if depth > config.max_depth:
                yield make_finding(
                    self,
                    graph,
                    f"Agent '{name}' sits at delegation depth {depth} (max {config.max_depth}).",
                    agent=name,
                    remediation="Flatten the hierarchy or merge intermediate routers.",
                )


@rule
class FanOut:
    """Too many children make routing decisions unreliable for the parent LLM."""

    id = "topology/fan-out"
    severity = Severity.WARNING
    summary = "Agent delegates to too many children"

    def check(self, graph: NetworkGraph, config: LintConfig) -> Iterable[Finding]:
        for name in graph.nodes:
            count = len(graph.children(name))
            if count > config.max_fan_out:
                yield make_finding(
                    self,
                    graph,
                    f"Agent '{name}' can delegate to {count} tools (max {config.max_fan_out}).",
                    agent=name,
                    remediation="Group children under intermediate specialists.",
                )


@rule
class DanglingTool:
    """A ``tools`` entry naming an agent that does not exist fails at runtime."""

    id = "topology/dangling-tool"
    severity = Severity.ERROR
    summary = "Tool reference points to an undefined agent"

    def check(self, graph: NetworkGraph, config: LintConfig) -> Iterable[Finding]:
        for edge in graph.edges:
            if edge.kind is EdgeKind.INTERNAL and edge.dst not in graph.nodes:
                yield make_finding(
                    self,
                    graph,
                    f"Agent '{edge.src}' lists tool '{edge.dst}', which is not defined in this network.",
                    agent=edge.src,
                    remediation="Define the agent, fix the typo, or reference it as an external '/network'.",
                )


@rule
class FrontManInvalid:
    """The first agent talks to the client; it must be an LLM agent."""

    id = "topology/front-man-invalid"
    severity = Severity.ERROR
    summary = "Front man is missing or is a coded tool / toolbox"

    def check(self, graph: NetworkGraph, config: LintConfig) -> Iterable[Finding]:
        if graph.front_man is None:
            yield make_finding(self, graph, "Network has no agents; there is no front man.")
            return
        node = graph.nodes[graph.front_man]
        if node.kind is not AgentKind.LLM_AGENT:
            yield make_finding(
                self,
                graph,
                f"Front man '{node.name}' is a {node.kind.value}; the first entry in 'tools' must be an LLM agent.",
                agent=node.name,
                remediation="Move an LLM agent to the top of the 'tools' list.",
            )
        elif not graph.children(node.name):
            yield make_finding(
                self,
                graph,
                f"Front man '{node.name}' has no tools; the network is a single agent.",
                agent=node.name,
                severity=Severity.INFO,
            )
