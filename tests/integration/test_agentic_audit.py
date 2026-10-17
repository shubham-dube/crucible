"""Crucible's own Neuro-SAN network driving a full audit (scripted = keyless; live needs ANTHROPIC_API_KEY)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from crucible.integrations.neurosan.loader import load_network
from crucible.services import toolkit
from crucible.services.agentic import network_path, run_agentic_audit
from crucible.topology.linter import lint

ZOO = Path(__file__).resolve().parents[2] / "examples" / "targets"


def test_crucible_network_lints_clean() -> None:
    result = lint(load_network(network_path()))
    assert [f for f in result.findings if f.severity.rank >= 2] == []


@pytest.mark.integration
@pytest.mark.usefixtures("crucible_home")
def test_scripted_agentic_audit_finds_leak() -> None:
    result = run_agentic_audit(ZOO, "account_leak", scripted=True)
    assert result.delegations[:2] == ("conductor -> topology_analyst", "topology_analyst -> lint_network")
    assert "test_runner -> run_audit" in result.delegations
    assert "fix_lead -> fix_verifier" in result.delegations
    assert "fix_verifier -> verify_fixes" in result.delegations
    assert len(result.audit_ids) == 1
    findings = toolkit.get_audit(result.audit_ids[0]).findings
    assert ("leak/sly-data-exposure", "profile_lookup") in {(f.rule_id, f.agent) for f in findings}
    assert result.report_path is not None
    assert Path(result.report_path).is_file()


@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
@pytest.mark.usefixtures("crucible_home")
def test_live_agentic_audit_fragile_weather() -> None:
    result = run_agentic_audit(ZOO, "fragile_weather")
    assert result.audit_ids
    rules = {f.rule_id for a in result.audit_ids for f in toolkit.get_audit(a).findings}
    assert "tool/error-masked" in rules
    assert result.answer
