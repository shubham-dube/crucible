"""Real Gemini round-trips (``pytest -m live``; skipped without GOOGLE_API_KEY). Costs a fraction of a cent."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from crucible.config import get_settings
from crucible.config.project import Project
from crucible.execution.budget import default_guard
from crucible.services.audit import AuditOptions, AuditService

LIVE = Path(__file__).resolve().parents[2] / "examples" / "live_targets"
ZOO = Path(__file__).resolve().parents[2] / "examples" / "targets"

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("GOOGLE_API_KEY"), reason="needs GOOGLE_API_KEY"),
    pytest.mark.usefixtures("crucible_home"),
]


def test_live_leak_is_proven_and_spend_recorded() -> None:
    service = AuditService(Project.load(LIVE))
    audit = service.audit_target(service.project.target("account_leak"), AuditOptions(timeout_s=90))
    assert "leak/sly-data-exposure" in {f.rule_id for f in audit.findings}
    assert default_guard().ledger.totals().cost_usd > 0


def test_target_llm_override_runs_a_scripted_zoo_network_on_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRUCIBLE_TARGET_LLM", "gemini:gemini-3.5-flash-lite")
    get_settings.cache_clear()
    service = AuditService(Project.load(ZOO))
    spec = service.project.target("clean_concierge")
    assert "llm_variants" in str(service.project.network_path(spec))
    audit = service.audit_target(spec, AuditOptions(timeout_s=90, scenario_ids=frozenset({"order-status"})))
    assert audit.batch is not None
    assert audit.batch.runs[0].tokens.cost_usd > 0
