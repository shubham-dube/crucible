"""Typed model of a Neuro-SAN agent network as a directed graph."""

from __future__ import annotations

from collections import deque
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentKind(StrEnum):
    """What kind of node an agent-network entry is."""

    LLM_AGENT = "llm_agent"
    CODED_TOOL = "coded_tool"
    TOOLBOX = "toolbox"
    EXTERNAL = "external"
    MCP = "mcp"


class EdgeKind(StrEnum):
    """How a parent reaches a child."""

    INTERNAL = "internal"
    EXTERNAL = "external"
    MCP = "mcp"


class AgentNode(BaseModel):
    """One agent / tool in the network."""

    model_config = ConfigDict(frozen=True)

    name: str
    kind: AgentKind
    description: str = ""
    instructions: str = ""
    parameters: dict[str, Any] | None = None
    class_ref: str | None = None
    toolbox: str | None = None
    tools: tuple[str, ...] = ()
    allow: dict[str, Any] = Field(default_factory=dict)
    llm_config: dict[str, Any] | None = None
    index: int = Field(default=-1, description="position in the HOCON tools list (-1 for synthetic nodes)")


class Edge(BaseModel):
    """A delegation edge parent -> child."""

    model_config = ConfigDict(frozen=True)

    src: str
    dst: str
    kind: EdgeKind = EdgeKind.INTERNAL


class NetworkLimits(BaseModel):
    """Top-level run budgets declared by the network."""

    model_config = ConfigDict(frozen=True)

    max_steps: int | None = None
    max_execution_seconds: float | None = None
    max_attempts: int | None = None
    request_timeout_seconds: float | None = None


class NetworkGraph(BaseModel):
    """The whole network: nodes, edges, front man and limits."""

    model_config = ConfigDict(frozen=True)

    name: str
    source_path: str | None = None
    front_man: str | None = None
    nodes: dict[str, AgentNode]
    edges: tuple[Edge, ...] = ()
    limits: NetworkLimits = Field(default_factory=NetworkLimits)
    config_hash: str | None = None

    def children(self, name: str) -> list[str]:
        """Direct delegation targets of ``name`` in declaration order."""
        return [e.dst for e in self.edges if e.src == name]

    def parents(self, name: str) -> list[str]:
        """Agents that can delegate to ``name``."""
        return [e.src for e in self.edges if e.dst == name]

    def reachable_from(self, start: str | None) -> set[str]:
        """All nodes reachable from ``start`` (inclusive)."""
        if start is None or start not in self.nodes:
            return set()
        seen = {start}
        queue = deque([start])
        while queue:
            for child in self.children(queue.popleft()):
                if child not in seen:
                    seen.add(child)
                    queue.append(child)
        return seen

    def depths(self) -> dict[str, int]:
        """Shortest delegation depth of each node reachable from the front man (front man = 0)."""
        if self.front_man is None:
            return {}
        out = {self.front_man: 0}
        queue = deque([self.front_man])
        while queue:
            node = queue.popleft()
            for child in self.children(node):
                if child not in out:
                    out[child] = out[node] + 1
                    queue.append(child)
        return out
