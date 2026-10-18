"""Patch application and deterministic proposers."""

from __future__ import annotations

import pytest
from tests.helpers import agent

from crucible.domain.errors import ConfigError
from crucible.domain.findings import Finding, Severity
from crucible.domain.fix import PatchOp, PatchOpKind
from crucible.fixes.apply import apply_ops, config_diff
from crucible.fixes.proposers import ADMIT_FAILURE, UNTRUSTED_TOOL_OUTPUT, propose
from crucible.integrations.neurosan.loader import build_graph

CONFIG = {
    "max_steps": 40,
    "tools": [
        agent("front", tools=["a", "b"], instructions="route"),
        agent("a", tools=["b"], instructions="do a", allow={"to_downstream": {"sly_data": True}}),
        agent("b", tools=["a"], instructions="do b", max_steps=40),
    ],
}
GRAPH = build_graph(CONFIG, "net")


def finding(rule: str, agent_name: str | None, message: str = "") -> Finding:
    return Finding(rule_id=rule, severity=Severity.ERROR, message=message, agent=agent_name)


def test_apply_ops_is_pure_and_complete() -> None:
    ops = [
        PatchOp(op=PatchOpKind.APPEND_INSTRUCTIONS, agent="a", value="be careful"),
        PatchOp(op=PatchOpKind.SET_DESCRIPTION, agent="b", value="new desc"),
        PatchOp(op=PatchOpKind.REMOVE_TOOL, agent="b", key="a"),
        PatchOp(op=PatchOpKind.SET_TOP_LEVEL, key="max_steps", value=100),
        PatchOp(op=PatchOpKind.SET_ALLOW_KEYS, agent="a", key="to_downstream", value=[]),
        PatchOp(op=PatchOpKind.SET_INSTRUCTIONS, agent="front", value="replaced"),
    ]
    out = apply_ops(CONFIG, ops)
    tools = {t["name"]: t for t in out["tools"]}
    assert tools["a"]["instructions"] == "do a\nbe careful"
    assert tools["b"]["function"]["description"] == "new desc"
    assert tools["b"]["tools"] == []
    assert out["max_steps"] == 100
    assert tools["b"]["max_steps"] == 100
    assert tools["a"]["allow"]["to_downstream"]["sly_data"] == []
    assert tools["front"]["instructions"] == "replaced"
    assert CONFIG["tools"][2]["tools"] == ["a"]  # original untouched
    assert "+" in config_diff(CONFIG, out, "net.hocon")


@pytest.mark.parametrize(
    "op",
    [
        PatchOp(op=PatchOpKind.REMOVE_TOOL, agent="a", key="zzz"),
        PatchOp(op=PatchOpKind.APPEND_INSTRUCTIONS, agent="ghost", value="x"),
        PatchOp(op=PatchOpKind.SET_TOP_LEVEL, value=1),
        PatchOp(op=PatchOpKind.SET_ALLOW_KEYS, agent="a", key="sideways", value=[]),
    ],
)
def test_invalid_ops(op: PatchOp) -> None:
    with pytest.raises(ConfigError):
        apply_ops(CONFIG, [op])


def test_cycle_proposal_removes_back_edge_and_dedupes() -> None:
    ping = finding("trace/ping-pong", "a", "'a' and 'b' delegated to each other 8 times")
    cycle = finding("topology/cycle-risk", "a", "Delegation cycle a -> b -> a")
    proposals = propose([ping, cycle], GRAPH, CONFIG)
    assert len(proposals) == 1
    ops = proposals[0].ops
    assert ops[0] == PatchOp(op=PatchOpKind.REMOVE_TOOL, agent="b", key="a")
    assert ops[1].agent == "b"


def test_instruction_and_manual_proposals() -> None:
    proposals = propose(
        [
            finding("tool/error-masked", "front"),
            finding("injection/instruction-followed", "a"),
            finding("leak/sly-data-exposure", "b"),
            finding("topology/sly-data-passthrough", "a", "Agent 'a' allows ALL sly_data to downstream."),
            finding("answer/missing-content", "front"),
        ],
        GRAPH,
        CONFIG,
    )
    by_rule = {p.rule_id: p for p in proposals}
    assert by_rule["tool/error-masked"].ops[0].value == ADMIT_FAILURE
    assert by_rule["injection/instruction-followed"].ops[0].value == UNTRUSTED_TOOL_OUTPUT
    assert by_rule["leak/sly-data-exposure"].manual
    assert by_rule["topology/sly-data-passthrough"].ops[0].key == "to_downstream"
    assert "answer/missing-content" not in by_rule


def test_budget_proposal_only_when_missing() -> None:
    unbounded = build_graph({"tools": [agent("f")]}, "n")
    proposal = propose([finding("topology/unbounded-budget", None)], unbounded, {"tools": []})[0]
    assert {o.key for o in proposal.ops} == {"max_execution_seconds", "max_steps"}
    bounded = build_graph({"tools": [agent("f")], "max_steps": 50, "max_execution_seconds": 30}, "n")
    assert propose([finding("trace/timeout", None)], bounded, {}) == []


def test_cycle_proposal_drops_instructions_naming_the_removed_agent() -> None:
    from tests.helpers import agent

    from crucible.integrations.neurosan.loader import build_graph
    from crucible.topology.rules import LintConfig, registry

    config = {
        "max_steps": 50,
        "max_execution_seconds": 60,
        "tools": [
            agent("desk", tools=["billing_expert", "payments_expert"]),
            agent("billing_expert", tools=["payments_expert"], instructions="Billing. Ask payments_expert."),
            agent("payments_expert", tools=["billing_expert"], instructions="Payments. Ask billing_expert."),
        ],
    }
    graph = build_graph(config, "t", "t.hocon")
    bounce = finding("trace/bounce", "billing_expert", "between 'billing_expert' and 'payments_expert' (1 / 1)")
    (proposal,) = propose([bounce], graph, config)
    patched = apply_ops(config, list(proposal.ops))
    payments = next(t for t in patched["tools"] if t["name"] == "payments_expert")
    assert "billing_expert" not in payments["instructions"]
    assert payments["instructions"].startswith("Payments.")
    fixed = build_graph(patched, "t", "t.hocon")
    for rule_id in ("topology/dangling-reference", "topology/cycle-risk"):
        assert list(registry.get(rule_id).check(fixed, LintConfig())) == []
