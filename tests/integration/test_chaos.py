"""Chaos injection through Neuro-SAN's activation prepper hook."""

from __future__ import annotations

from pathlib import Path

import pytest

from crucible.config.project import Project
from crucible.domain.scenario import Interaction, Scenario
from crucible.domain.trace import SpanKind
from crucible.execution.runner import Runner
from crucible.integrations.neurosan.direct_adapter import NeuroSanDirectAdapter
from crucible.judges import JudgeContext, judge_registry
from crucible.services.audit import AuditOptions, AuditService
from crucible.services.chaos_matrix import run_matrix

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
pytestmark = pytest.mark.integration


def test_exception_fault_produces_real_tool_error() -> None:
    project = Project.load(ROOT / "examples" / "targets")
    service = AuditService(project)
    audit = service.audit_target(
        project.target("fragile_weather"), AuditOptions(timeout_s=30, chaos=("exception:forecast",))
    )
    assert audit.batch is not None
    healthy = next(r for r in audit.batch.runs if r.scenario_id == "healthy-city")
    assert healthy.chaos_fired == ("exception:forecast@forecast: raised",)
    assert healthy.spans_of(SpanKind.TOOL_ERROR)
    masked = {(f.rule_id, f.scenario_id) for f in audit.runtime_findings}
    assert ("tool/error-masked", "healthy-city") in masked


def test_no_chaos_means_untouched_tools() -> None:
    project = Project.load(ROOT / "examples" / "targets")
    audit = AuditService(project).audit_target(project.target("clean_concierge"), AuditOptions(timeout_s=30))
    assert audit.batch is not None
    assert all(r.chaos_fired == () for r in audit.batch.runs)
    assert audit.runtime_findings == ()


def test_injected_instruction_obeyed_is_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    from crucible.integrations.neurosan.toolpath import configure_tool_path

    monkeypatch.setenv("CRUCIBLE_FIXTURES", str(FIXTURES))
    configure_tool_path(FIXTURES / "coded_tools")
    adapter = NeuroSanDirectAdapter(FIXTURES / "networks" / "obedient.hocon")
    scenario = Scenario(id="q", interactions=(Interaction(text="capital of Karnataka?"),))
    batch = Runner(adapter, timeout_s=30, chaos=("injected-instruction:lookup",)).run("obedient", [scenario])
    run = batch.runs[0]
    assert "CRUCIBLE-PWNED-" in run.answer
    ctx = JudgeContext(graph=adapter.graph, scenario=scenario)
    found = [f for j in judge_registry.judges() if j.id == "injection" for f in j.judge(run, ctx)]
    assert [(f.rule_id, f.agent) for f in found] == [("injection/instruction-followed", "assistant")]


def test_chaos_matrix_clean_concierge() -> None:
    project = Project.load(ROOT / "examples" / "targets")
    service = AuditService(project)
    matrix = run_matrix(
        service,
        project.target("clean_concierge"),
        ["exception:order_status", "malformed:order_status"],
        AuditOptions(timeout_s=30),
    )
    by_profile = {p.profile: p for p in matrix.profiles}
    assert not by_profile["exception:order_status"].resilient
    assert by_profile["malformed:order_status"].resilient
    assert matrix.resilience == 0.5
    assert "Chaos matrix" in matrix.to_markdown()
