"""Semantic rules: descriptions, routing clarity and tool schemas."""

from __future__ import annotations

import re
from collections.abc import Iterable
from itertools import combinations

from crucible.domain.findings import Finding, Severity
from crucible.domain.network import AgentKind, NetworkGraph
from crucible.topology.rules.base import LintConfig, make_finding, rule

_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "for",
        "from",
        "handles",
        "help",
        "helps",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "with",
        "you",
        "your",
        "agent",
        "agents",
        "tool",
        "tools",
        "user",
        "users",
        "question",
        "questions",
        "request",
        "requests",
        "about",
        "any",
        "all",
    ]
)
_TOKEN = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> set[str]:
    """Content words of a description (lower-cased, stopwords removed)."""
    return {t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2}


def jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity of two token sets (0 when either is empty)."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@rule
class RoutingOverlap:
    """Parents route by reading child descriptions; near-duplicates make the choice a coin flip."""

    id = "topology/routing-overlap"
    severity = Severity.WARNING
    summary = "Sibling agents have overlapping descriptions (ambiguous routing)"

    def check(self, graph: NetworkGraph, config: LintConfig) -> Iterable[Finding]:
        for parent in graph.nodes:
            siblings = [c for c in graph.children(parent) if c in graph.nodes and graph.nodes[c].description]
            for left, right in combinations(siblings, 2):
                score = jaccard(tokens(graph.nodes[left].description), tokens(graph.nodes[right].description))
                if score >= config.routing_overlap_threshold:
                    yield make_finding(
                        self,
                        graph,
                        f"'{left}' and '{right}' (children of '{parent}') have {score:.0%} description overlap; "
                        f"'{parent}' may route to the wrong one.",
                        agent=parent,
                        remediation="Make each description state what it handles AND what it does not.",
                    )


@rule
class WeakDescription:
    """The function description is the routing contract; empty or trivial ones break delegation."""

    id = "topology/weak-description"
    severity = Severity.WARNING
    summary = "Agent description is missing or too short to route on"

    def check(self, graph: NetworkGraph, config: LintConfig) -> Iterable[Finding]:
        for name, node in graph.nodes.items():
            if node.index < 0 or name == graph.front_man:
                continue
            text = node.description.strip()
            normalized = text.lower().replace(" ", "_")
            if len(text) < config.min_description_chars or normalized == name.lower():
                yield make_finding(
                    self,
                    graph,
                    f"Agent '{name}' has a weak description ({len(text)} chars): {text!r}.",
                    agent=name,
                    remediation="Describe the agent's responsibility, inputs and boundaries in one or two sentences.",
                )


@rule
class ToolMissingParams:
    """Coded tools without a parameter schema get free-form, often hallucinated, arguments."""

    id = "topology/tool-missing-params"
    severity = Severity.WARNING
    summary = "Coded tool declares no parameter schema"

    def check(self, graph: NetworkGraph, config: LintConfig) -> Iterable[Finding]:
        for name, node in graph.nodes.items():
            if node.kind is AgentKind.CODED_TOOL and not (node.parameters or {}).get("properties"):
                yield make_finding(
                    self,
                    graph,
                    f"Coded tool '{name}' has no function.parameters properties.",
                    agent=name,
                    remediation="Declare function.parameters with types, descriptions and 'required'.",
                )
