"""Load a Neuro-SAN HOCON network into Crucible's typed ``NetworkGraph``."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from crucible.domain.errors import NetworkLoadError
from crucible.domain.network import AgentKind, AgentNode, Edge, EdgeKind, NetworkGraph, NetworkLimits


@dataclass(frozen=True)
class LoadedNetwork:
    """A parsed network: the typed graph plus the fully resolved raw config (includes/commondefs applied)."""

    graph: NetworkGraph
    raw_config: dict[str, Any]
    path: Path


def classify_tool_ref(ref: str) -> EdgeKind:
    """Classify a ``tools`` entry: internal agent name, external network, or MCP server."""
    lowered = ref.lower()
    is_url = lowered.startswith(("http://", "https://"))
    if is_url and ("mcp" in lowered.split("/")[2].split(".") or "/mcp" in lowered):
        return EdgeKind.MCP
    if is_url or ref.startswith("/"):
        return EdgeKind.EXTERNAL
    return EdgeKind.INTERNAL


def _tool_ref_name(entry: Any) -> str | None:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict) and isinstance(entry.get("url"), str):
        return str(entry["url"])
    return None


def _agent_kind(spec: dict[str, Any]) -> AgentKind:
    if spec.get("class"):
        return AgentKind.CODED_TOOL
    if spec.get("toolbox"):
        return AgentKind.TOOLBOX
    return AgentKind.LLM_AGENT


def _as_float(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def _as_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int) else None


def build_graph(config: dict[str, Any], name: str, source_path: str | None = None) -> NetworkGraph:
    """Build a ``NetworkGraph`` from a resolved Neuro-SAN network config dict (pure function)."""
    specs = [s for s in config.get("tools") or [] if isinstance(s, dict)]
    nodes: dict[str, AgentNode] = {}
    edges: list[Edge] = []
    synthetic: dict[str, AgentNode] = {}
    for index, spec in enumerate(specs):
        agent_name = str(spec.get("name", f"<unnamed-{index}>"))
        raw_function = spec.get("function")
        function: dict[str, Any] = raw_function if isinstance(raw_function, dict) else {}
        tool_refs = [r for r in (_tool_ref_name(t) for t in spec.get("tools") or []) if r]
        nodes[agent_name] = AgentNode(
            name=agent_name,
            kind=_agent_kind(spec),
            description=str(function.get("description", "") or ""),
            instructions=str(spec.get("instructions", "") or ""),
            parameters=function.get("parameters") if isinstance(function.get("parameters"), dict) else None,
            class_ref=spec.get("class"),
            toolbox=spec.get("toolbox"),
            tools=tuple(tool_refs),
            allow=spec.get("allow") if isinstance(spec.get("allow"), dict) else {},
            llm_config=spec.get("llm_config") if isinstance(spec.get("llm_config"), dict) else None,
            index=index,
        )
        for ref in tool_refs:
            kind = classify_tool_ref(ref)
            edges.append(Edge(src=agent_name, dst=ref, kind=kind))
            if kind is not EdgeKind.INTERNAL and ref not in synthetic:
                node_kind = AgentKind.MCP if kind is EdgeKind.MCP else AgentKind.EXTERNAL
                synthetic[ref] = AgentNode(name=ref, kind=node_kind)
    for ref, node in synthetic.items():
        nodes.setdefault(ref, node)

    front_man = str(specs[0].get("name")) if specs and specs[0].get("name") else None
    limits = NetworkLimits(
        max_steps=_as_int(config.get("max_steps")),
        max_execution_seconds=_as_float(config.get("max_execution_seconds")),
        max_attempts=_as_int(config.get("max_attempts")),
        request_timeout_seconds=_as_float(config.get("request_timeout_seconds")),
    )
    digest = hashlib.sha256(json.dumps(config, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return NetworkGraph(
        name=name,
        source_path=source_path,
        front_man=front_man,
        nodes=nodes,
        edges=tuple(edges),
        limits=limits,
        config_hash=digest,
    )


def load_config(path: str | Path) -> dict[str, Any]:
    """Parse a HOCON network file with Neuro-SAN's restorer (includes, env substitution, commondefs applied)."""
    from neuro_san.internals.graph.persistence.agent_network_restorer import AgentNetworkRestorer

    file_path = Path(path).resolve()
    if not file_path.is_file():
        raise NetworkLoadError(f"network file not found: {file_path}")
    try:
        network = AgentNetworkRestorer(registry_dir=str(file_path.parent)).restore(file_reference=str(file_path))
    except Exception as exc:  # restorer raises a variety of parse errors
        raise NetworkLoadError(f"could not parse {file_path}: {exc}") from exc
    if network is None:
        raise NetworkLoadError(f"empty network config: {file_path}")
    config = network.get_config()
    if not isinstance(config, dict):
        raise NetworkLoadError(f"network config is not an object: {file_path}")
    return dict(config)


def load_network(path: str | Path) -> LoadedNetwork:
    """Load a network file into a ``LoadedNetwork``."""
    file_path = Path(path).resolve()
    config = load_config(file_path)
    graph = build_graph(config, name=file_path.stem, source_path=str(file_path))
    return LoadedNetwork(graph=graph, raw_config=config, path=file_path)
