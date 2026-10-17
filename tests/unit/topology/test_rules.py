"""Unit tests for every built-in lint rule."""

from __future__ import annotations

from tests.helpers import agent, make_graph

from crucible.domain.findings import Severity
from crucible.topology.rules import LintConfig, registry

CFG = LintConfig()
LIMITS = {"max_steps": 50, "max_execution_seconds": 60}


def ids(rule_id: str, graph, config: LintConfig = CFG) -> list[str]:  # type: ignore[no-untyped-def]
    return [f.agent or "" for f in registry.get(rule_id).check(graph, config)]


def test_cycle_risk_detects_two_agent_cycle() -> None:
    g = make_graph(agent("front", tools=["a"]), agent("a", tools=["b"]), agent("b", tools=["a"]), **LIMITS)
    findings = list(registry.get("topology/cycle-risk").check(g, CFG))
    assert len(findings) == 1
    assert "a -> b -> a" in findings[0].message or "b -> a -> b" in findings[0].message


def test_no_cycle_in_tree() -> None:
    g = make_graph(agent("front", tools=["a", "b"]), agent("a"), agent("b"))
    assert ids("topology/cycle-risk", g) == []


def test_unreachable_agent() -> None:
    g = make_graph(agent("front", tools=["a"]), agent("a"), agent("lonely"))
    assert ids("topology/unreachable-agent", g) == ["lonely"]


def test_max_depth() -> None:
    chain = [agent(f"n{i}", tools=[f"n{i + 1}"]) for i in range(6)] + [agent("n6")]
    g = make_graph(*chain)
    assert ids("topology/max-depth", g) == ["n5", "n6"]
    assert ids("topology/max-depth", g, LintConfig(max_depth=10)) == []


def test_fan_out() -> None:
    kids = [f"k{i}" for i in range(9)]
    g = make_graph(agent("front", tools=kids), *[agent(k) for k in kids])
    assert ids("topology/fan-out", g) == ["front"]


def test_dangling_tool_ignores_external_and_mcp() -> None:
    g = make_graph(agent("front", tools=["ghost", "/other_net", "https://mcp.example.com/mcp"]))
    assert ids("topology/dangling-tool", g) == ["front"]


def test_front_man_coded_tool_is_error() -> None:
    g = make_graph({"name": "tool", "class": "x.Y", "function": {"description": "a tool"}})
    findings = list(registry.get("topology/front-man-invalid").check(g, CFG))
    assert findings[0].severity is Severity.ERROR


def test_front_man_without_tools_is_info() -> None:
    g = make_graph(agent("solo"))
    findings = list(registry.get("topology/front-man-invalid").check(g, CFG))
    assert findings[0].severity is Severity.INFO


def test_empty_network_has_no_front_man() -> None:
    g = make_graph()
    assert len(list(registry.get("topology/front-man-invalid").check(g, CFG))) == 1


def test_routing_overlap() -> None:
    g = make_graph(
        agent("front", tools=["a", "b", "c"]),
        agent("a", "Answers billing invoice refund payment questions."),
        agent("b", "Answers payment refund billing invoice questions."),
        agent("c", "Books flights and hotel reservations for travel."),
    )
    findings = list(registry.get("topology/routing-overlap").check(g, CFG))
    assert len(findings) == 1
    assert "'a' and 'b'" in findings[0].message


def test_weak_description_skips_front_man() -> None:
    g = make_graph(agent("front", "x", tools=["a", "b"]), agent("a", "db"), agent("b", "Retrieves invoices by id."))
    assert ids("topology/weak-description", g) == ["a"]


def test_tool_missing_params() -> None:
    good = {"name": "t1", "class": "m.T", "function": {"description": "d", "parameters": {"properties": {"x": {}}}}}
    bad = {"name": "t2", "class": "m.T", "function": {"description": "d"}}
    g = make_graph(agent("front", tools=["t1", "t2"]), good, bad)
    assert ids("topology/tool-missing-params", g) == ["t2"]


def test_unbounded_budget() -> None:
    assert len(list(registry.get("topology/unbounded-budget").check(make_graph(agent("f")), CFG))) == 2
    assert list(registry.get("topology/unbounded-budget").check(make_graph(agent("f"), **LIMITS), CFG)) == []


def test_sly_data_passthrough_wildcards() -> None:
    g = make_graph(
        agent("front", tools=["a", "b", "c"]),
        agent("a", allow={"to_downstream": {"sly_data": True}}),
        agent("b", allow={"to_tracing": {"sly_data": ["*"]}}),
        agent("c", allow={"to_downstream": {"sly_data": ["account_id"]}}),
    )
    findings = list(registry.get("topology/sly-data-passthrough").check(g, CFG))
    assert {(f.agent, f.severity) for f in findings} == {("a", Severity.WARNING), ("b", Severity.ERROR)}


def test_findings_carry_location() -> None:
    g = make_graph(agent("front", tools=["a"]), agent("a"), agent("lonely"))
    finding = next(iter(registry.get("topology/unreachable-agent").check(g, CFG)))
    assert finding.location.file == "test.hocon"
    assert finding.location.json_path == "tools[2]"
