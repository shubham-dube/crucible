"""Shared test helpers."""

from __future__ import annotations

from typing import Any

from crucible.domain.network import NetworkGraph
from crucible.integrations.neurosan.loader import build_graph


def agent(name: str, description: str = "", tools: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    """An agent spec dict as it appears in a HOCON ``tools`` list."""
    spec: dict[str, Any] = {"name": name, "function": {"description": description or f"{name} handles {name} work."}}
    if tools:
        spec["tools"] = tools
    spec.update(extra)
    return spec


def make_graph(*specs: dict[str, Any], **top: Any) -> NetworkGraph:
    """Build a graph from agent specs (first = front man) plus top-level keys."""
    return build_graph({"tools": list(specs), **top}, name="test", source_path="test.hocon")
