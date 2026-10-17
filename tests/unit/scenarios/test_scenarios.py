"""Coverage, template generation and interchange formats."""

from __future__ import annotations

from pathlib import Path

from tests.helpers import agent, make_graph

from crucible.domain.scenario import Expectation, Interaction, Scenario, ScenarioSource, ScenarioSuite
from crucible.domain.trace import RunBatch, RunResult, Span, SpanKind
from crucible.scenarios.coverage import coverage, edges
from crucible.scenarios.generator import TemplateGenerator
from crucible.scenarios.io import from_neurosan_test, merge_suites, to_neurosan_test, write_suite

GRAPH = make_graph(
    agent("front", tools=["a", "b"]),
    agent("a", "Handles refunds for damaged items. Not for billing.", tools=["c"]),
    agent("b", "Answers billing questions."),
    agent("c", "Looks up order records by id."),
    agent("orphan"),
)


def test_edges_with_routes() -> None:
    planned = {(e.src, e.dst): e.route for e in edges(GRAPH)}
    assert planned == {("front", "a"): ("a",), ("front", "b"): ("b",), ("a", "c"): ("a", "c")}


def test_coverage_from_batch() -> None:
    span = Span(id="s1", seq=1, kind=SpanKind.DELEGATION, agent="front", target="a")
    batch = RunBatch(
        batch_id="b",
        target="t",
        started_at="x",
        runs=(RunResult(run_id="r", target="t", scenario_id="s", spans=(span,)),),
    )
    report = coverage(GRAPH, [batch])
    assert report.ratio == 1 / 3
    assert {(e.src, e.dst) for e in report.uncovered} == {("front", "b"), ("a", "c")}


def test_template_generator_targets_uncovered_edges() -> None:
    uncovered = [e for e in edges(GRAPH) if e.dst == "c"]
    scenarios = TemplateGenerator().generate(GRAPH, uncovered)
    edge_case = scenarios[0]
    assert edge_case.target_edge == ("a", "c")
    assert edge_case.expect.route == ("a", "c")
    assert "looks up order records by id" in edge_case.interactions[0].text
    assert edge_case.source is ScenarioSource.GENERATED
    ids = {s.id for s in scenarios}
    assert {"probe-off-topic", "probe-user-injection", "probe-sly-data"} <= ids
    sly = next(s for s in scenarios if s.id == "probe-sly-data")
    assert sly.interactions[0].sly_data["account_secret"] in sly.expect.answer_not_contains


def test_generator_without_probes() -> None:
    assert len(TemplateGenerator(include_probes=False).generate(GRAPH)) == 3


SCENARIO = Scenario(
    id="refund",
    description="refund flow",
    interactions=(Interaction(text="refund please", sly_data={"k": "v"}), Interaction(text="thanks")),
    expect=Expectation(route=("a",), answer_contains=("refund",), answer_not_contains=("secret",)),
    tags=("x",),
)


def test_neurosan_roundtrip() -> None:
    case = to_neurosan_test(SCENARIO, "net")
    assert case["agent"] == "net"
    assert case["interactions"][1]["continue_conversation"] is True
    assert case["interactions"][1]["response"]["text"] == {"keywords": ["refund"], "not_keywords": ["secret"]}
    assert from_neurosan_test(case) == SCENARIO


def test_suite_yaml_roundtrip(tmp_path: Path) -> None:
    import yaml

    suite = merge_suites(ScenarioSuite(scenarios=(SCENARIO,)), [SCENARIO, SCENARIO.model_copy(update={"id": "two"})])
    assert [s.id for s in suite.scenarios] == ["refund", "two"]
    path = write_suite(suite, tmp_path / "s.yaml")
    assert ScenarioSuite.model_validate(yaml.safe_load(path.read_text())) == suite
