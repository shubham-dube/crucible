"""Fault parsing, catalog behaviour and plan state."""

from __future__ import annotations

import pytest

from crucible.chaos import catalog, state
from crucible.domain.chaos import FaultKind, FaultSpec, parse_fault
from crucible.domain.errors import ConfigError


def test_parse_fault_variants() -> None:
    spec = parse_fault("latency:order_*:seconds=2:p=0.5")
    assert spec.kind is FaultKind.LATENCY
    assert spec.target == "order_*"
    assert spec.params == {"seconds": 2}
    assert spec.probability == 0.5
    assert spec.applies_to("order_status")
    assert not spec.applies_to("policy")
    assert parse_fault("exception").target == "*"
    assert parse_fault(spec.id) == spec


def test_parse_fault_errors() -> None:
    with pytest.raises(ConfigError, match="unknown fault"):
        parse_fault("explode:x")
    with pytest.raises(ConfigError):
        parse_fault("")


def test_before_call_faults() -> None:
    sly = {"a": "1", "b": "2", "crucible_canary": "c"}
    with pytest.raises(catalog.InjectedFailureError):
        catalog.before_call(FaultSpec(kind=FaultKind.EXCEPTION), {}, sly)
    with pytest.raises(TimeoutError):
        catalog.before_call(FaultSpec(kind=FaultKind.TIMEOUT), {}, sly)
    catalog.before_call(FaultSpec(kind=FaultKind.SLY_DROP, params={"keys": "a"}), {}, sly)
    assert "a" not in sly
    catalog.before_call(FaultSpec(kind=FaultKind.SLY_MUTATE), {}, sly)
    assert sly == {"b": catalog.MUTATED, "crucible_canary": "c"}
    assert catalog.delay_seconds(FaultSpec(kind=FaultKind.LATENCY, params={"seconds": 3})) == 3.0
    assert catalog.delay_seconds(FaultSpec(kind=FaultKind.EMPTY)) is None


def test_after_call_faults() -> None:
    assert catalog.after_call(FaultSpec(kind=FaultKind.EMPTY), "data")[0] == ""
    malformed, _ = catalog.after_call(FaultSpec(kind=FaultKind.MALFORMED), "abcdef")
    assert malformed.startswith("abc")
    assert malformed.isprintable()
    big, _ = catalog.after_call(FaultSpec(kind=FaultKind.OVERSIZED, params={"chars": 1000}), "x")
    assert len(big) == 1000
    injected, note = catalog.after_call(FaultSpec(kind=FaultKind.INJECTED_INSTRUCTION), "fact", "CRUCIBLE-PWNED-AA")
    assert "CRUCIBLE-PWNED-AA" in injected
    assert note == "marker=CRUCIBLE-PWNED-AA"
    assert catalog.after_call(FaultSpec(kind=FaultKind.LATENCY), "same") == ("same", None)


def test_plan_selection_is_seeded() -> None:
    faults = [FaultSpec(kind=FaultKind.EXCEPTION, target="t", probability=0.5)]
    picks_a = [state.activate(faults, seed="s1").select("t") is not None for _ in range(1)]
    plan = state.activate(faults, seed="seed")
    first = [plan.select("t") is not None for _ in range(20)]
    plan = state.activate(faults, seed="seed")
    assert [plan.select("t") is not None for _ in range(20)] == first
    assert plan.select("other") is None
    assert picks_a
    state.deactivate()
    assert state.current() is None
