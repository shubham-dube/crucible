"""NetworkGraph helpers."""

from __future__ import annotations

from tests.helpers import agent, make_graph


def test_reachability_and_depths() -> None:
    g = make_graph(agent("f", tools=["a"]), agent("a", tools=["b"]), agent("b"), agent("x"))
    assert g.reachable_from("f") == {"f", "a", "b"}
    assert g.depths() == {"f": 0, "a": 1, "b": 2}
    assert g.parents("b") == ["a"]
    assert g.reachable_from(None) == set()
