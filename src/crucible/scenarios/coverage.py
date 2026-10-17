"""Delegation-edge coverage: which parts of the network a scenario set actually exercises."""

from __future__ import annotations

from collections import deque

from pydantic import BaseModel, ConfigDict

from crucible.domain.network import AgentKind, EdgeKind, NetworkGraph
from crucible.domain.trace import RunBatch, SpanKind


class CoverageEdge(BaseModel):
    """A delegation edge plus the shortest route from the front man that reaches its child."""

    model_config = ConfigDict(frozen=True)

    src: str
    dst: str
    route: tuple[str, ...]
    child_kind: AgentKind


class CoverageReport(BaseModel):
    """Planned edges vs. edges seen in traces."""

    model_config = ConfigDict(frozen=True)

    edges: tuple[CoverageEdge, ...]
    covered: tuple[CoverageEdge, ...]

    @property
    def uncovered(self) -> list[CoverageEdge]:
        """Edges never exercised."""
        return [e for e in self.edges if e not in self.covered]

    @property
    def ratio(self) -> float:
        """Covered share of edges (1.0 when the network has no edges)."""
        return len(self.covered) / len(self.edges) if self.edges else 1.0


def edges(graph: NetworkGraph) -> list[CoverageEdge]:
    """Internal edges reachable from the front man, each with its shortest route (agents after the front man)."""
    if graph.front_man is None:
        return []
    routes: dict[str, tuple[str, ...]] = {graph.front_man: ()}
    queue = deque([graph.front_man])
    out: list[CoverageEdge] = []
    seen: set[tuple[str, str]] = set()
    while queue:
        node = queue.popleft()
        for edge in graph.edges:
            if edge.src != node or edge.kind is not EdgeKind.INTERNAL or edge.dst not in graph.nodes:
                continue
            if (edge.src, edge.dst) in seen:
                continue
            seen.add((edge.src, edge.dst))
            route = (*routes[node], edge.dst)
            out.append(CoverageEdge(src=edge.src, dst=edge.dst, route=route, child_kind=graph.nodes[edge.dst].kind))
            if edge.dst not in routes:
                routes[edge.dst] = route
                queue.append(edge.dst)
    return out


def coverage(graph: NetworkGraph, batches: list[RunBatch]) -> CoverageReport:
    """Which planned edges appear as delegations in the given batches."""
    exercised = {
        (s.agent, s.target)
        for batch in batches
        for run in batch.runs
        for s in run.spans
        if s.kind is SpanKind.DELEGATION
    }
    planned = edges(graph)
    return CoverageReport(edges=tuple(planned), covered=tuple(e for e in planned if (e.src, e.dst) in exercised))
