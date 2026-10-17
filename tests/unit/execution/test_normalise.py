"""Normaliser on real recorded Neuro-SAN MAXIMAL streams."""

from __future__ import annotations

import json
from pathlib import Path

from crucible.domain.trace import SpanKind
from crucible.integrations.neurosan.normalise import Normaliser, agent_of, origin_path

TRACES = Path(__file__).resolve().parents[2] / "fixtures" / "traces"


def _normalise(name: str) -> Normaliser:
    normaliser = Normaliser()
    for message in json.loads((TRACES / f"{name}.json").read_text()):
        normaliser.feed(message)
    return normaliser


def test_origin_helpers() -> None:
    path = origin_path([{"tool": "a", "instantiation_index": 1}, {"tool": "b", "instantiation_index": 2}])
    assert path == ("a#1", "b#2")
    assert agent_of(path) == "b"
    assert origin_path(None) == ()


def test_tool_error_trace() -> None:
    n = _normalise("fragile_outage")
    kinds = [s.kind for s in n.spans]
    assert SpanKind.DELEGATION in kinds
    error = next(s for s in n.spans if s.kind is SpanKind.TOOL_ERROR)
    assert error.agent == "forecast"
    assert "503" in error.text
    delegation = next(s for s in n.spans if s.kind is SpanKind.DELEGATION)
    assert (delegation.agent, delegation.target) == ("weather_desk", "forecast")
    assert delegation.data["params"] == {"city": "Raichur"}
    returned = next(s for s in n.spans if s.kind is SpanKind.TOOL_RETURN)
    assert returned.agent == "weather_desk"
    assert returned.target == "forecast"
    assert "sunny" in n.answer
    assert n.tokens.total > 0


def test_injection_trace_has_two_delegations() -> None:
    n = _normalise("injection")
    targets = [s.target for s in n.spans if s.kind is SpanKind.DELEGATION]
    assert targets == ["web_fetch", "send_email"]
    args = next(s for s in n.spans if s.kind is SpanKind.TOOL_ARGS and s.agent == "send_email")
    assert args.data["args"]["to"] == "exfil@attacker.test"
    assert "origin" not in args.data["args"]


def test_nested_llm_agent_trace() -> None:
    n = _normalise("nested_agent")
    outputs = {s.agent for s in n.spans if s.kind is SpanKind.LLM_OUTPUT}
    assert {"helpdesk", "billing_expert"} <= outputs
    systems = {s.agent for s in n.spans if s.kind is SpanKind.SYSTEM_PROMPT}
    assert "billing_expert" in systems
    assert [s.seq for s in n.spans] == list(range(1, len(n.spans) + 1))


def test_empty_message_ignored() -> None:
    n = Normaliser()
    n.feed({})
    assert n.spans == []
