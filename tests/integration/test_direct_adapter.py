"""Direct adapter against the bug zoo: traces, prompt capture, timeouts, session reuse."""

from __future__ import annotations

from pathlib import Path

import pytest

from crucible.config.project import Project
from crucible.domain.trace import RunStatus, SpanKind
from crucible.execution.runner import Runner
from crucible.integrations.neurosan.direct_adapter import NeuroSanDirectAdapter

ZOO = Path(__file__).resolve().parents[2] / "examples" / "targets"
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def project() -> Project:
    p = Project.load(ZOO)
    p.activate()
    return p


def _batch(project: Project, target: str, timeout: float = 60.0):  # type: ignore[no-untyped-def]
    spec = project.target(target)
    adapter = NeuroSanDirectAdapter(project.network_path(spec))
    return Runner(adapter, timeout_s=timeout).run(target, project.scenarios(spec).scenarios), adapter


def test_leak_secret_visible_in_captured_llm_input(project: Project) -> None:
    batch, _ = _batch(project, "account_leak")
    run = batch.runs[0]
    assert run.status is RunStatus.OK
    assert len(run.llm_calls) == 2
    assert all(c.agent == "account_concierge" for c in run.llm_calls)
    assert "SYNTH-ID-4417-2290" in run.llm_calls[1].text
    assert "SYNTH-ID-4417-2290" not in run.llm_calls[0].text
    planted = next(sv for sv in run.sensitive if sv.planted)
    assert planted.value not in run.answer


def test_session_reused_across_runs(project: Project) -> None:
    batch, adapter = _batch(project, "clean_concierge")
    assert [r.status for r in batch.runs] == [RunStatus.OK, RunStatus.OK]
    assert adapter._session is not None
    assert [r.delegations() for r in batch.runs] == [[("concierge", "order_status")], [("concierge", "policy_expert")]]


def test_framework_timeout_detected(project: Project) -> None:
    batch, _ = _batch(project, "support_loop")
    loop = next(r for r in batch.runs if r.scenario_id == "refund-request")
    assert loop.status is RunStatus.TIMEOUT
    assert len(loop.delegations()) > 10
    ok = next(r for r in batch.runs if r.scenario_id == "invoice-copy")
    assert ok.status is RunStatus.OK


def test_hard_timeout_closes_session_and_recovers(project: Project) -> None:
    spec = project.target("support_loop")
    adapter = NeuroSanDirectAdapter(project.network_path(spec))
    scenarios = project.scenarios(spec).scenarios
    batch = Runner(adapter, timeout_s=1.0).run("support_loop", scenarios)
    loop = next(r for r in batch.runs if r.scenario_id == "refund-request")
    assert loop.status is RunStatus.TIMEOUT
    assert loop.error
    assert "hard timeout" in loop.error
    after = next(r for r in batch.runs if r.scenario_id == "invoice-copy")
    assert after.status is RunStatus.OK
    assert any(s.kind is SpanKind.FINAL_ANSWER for s in after.spans)
