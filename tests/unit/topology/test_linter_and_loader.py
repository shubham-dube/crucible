"""Linter orchestration and graph building."""

from __future__ import annotations

import pytest
from tests.helpers import agent

from crucible.domain.findings import Severity
from crucible.domain.network import AgentKind, EdgeKind
from crucible.integrations.neurosan.loader import LoadedNetwork, build_graph, classify_tool_ref
from crucible.topology.linter import lint
from crucible.topology.rules import LintConfig


@pytest.mark.parametrize(
    ("ref", "kind"),
    [
        ("billing", EdgeKind.INTERNAL),
        ("/other", EdgeKind.EXTERNAL),
        ("http://host:8080/net", EdgeKind.EXTERNAL),
        ("https://mcp.deepwiki.com/mcp", EdgeKind.MCP),
        ("https://api.example.com/mcp", EdgeKind.MCP),
    ],
)
def test_classify_tool_ref(ref: str, kind: EdgeKind) -> None:
    assert classify_tool_ref(ref) is kind


def test_build_graph_kinds_and_synthetic_nodes() -> None:
    g = build_graph(
        {"tools": [agent("f", tools=["t", "/ext"]), {"name": "t", "class": "m.T", "function": {"description": "x"}}]},
        name="n",
    )
    assert g.front_man == "f"
    assert g.nodes["t"].kind is AgentKind.CODED_TOOL
    assert g.nodes["/ext"].kind is AgentKind.EXTERNAL
    assert g.nodes["/ext"].index == -1
    assert g.config_hash


def _loaded(*specs, **top) -> LoadedNetwork:  # type: ignore[no-untyped-def]
    from pathlib import Path

    config = {"tools": list(specs), **top}
    return LoadedNetwork(graph=build_graph(config, "n", "n.hocon"), raw_config=config, path=Path("n.hocon"))


def test_lint_sorted_and_disable() -> None:
    loaded = _loaded(agent("f", tools=["ghost"]))
    result = lint(loaded, LintConfig(run_neurosan_validators=False))
    assert result.findings[0].severity is Severity.ERROR
    assert result.fails(Severity.ERROR)
    disabled = lint(loaded, LintConfig(disabled=frozenset({"topology/dangling-tool"}), run_neurosan_validators=False))
    assert all(f.rule_id != "topology/dangling-tool" for f in disabled.findings)
    assert not result.fails(None)


def test_neurosan_duplicates_suppressed_when_rule_active() -> None:
    loaded = _loaded(agent("f", tools=["ghost"]), agent("orphan"))
    rules = [f.rule_id for f in lint(loaded).findings]
    assert "neurosan/validator" not in rules
    with_dupes = lint(loaded, LintConfig(disabled=frozenset({"topology/dangling-tool"})))
    assert "neurosan/validator" in [f.rule_id for f in with_dupes.findings]
