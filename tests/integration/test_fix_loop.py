"""Verified fix loop on the bug zoo (keyless: scripted models obey remediation instructions)."""

from __future__ import annotations

from pathlib import Path

import pytest

from crucible.config.project import Project
from crucible.services.audit import AuditOptions, AuditService
from crucible.services.fixing import fix_target

ZOO = Path(__file__).resolve().parents[2] / "examples" / "targets"
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def service() -> AuditService:
    return AuditService(Project.load(ZOO))


@pytest.mark.parametrize(
    ("target", "rule", "resolves"),
    [
        ("support_loop", "trace/ping-pong", {"trace/ping-pong", "trace/timeout", "budget/delegations"}),
        ("fragile_weather", "tool/error-masked", {"tool/error-masked"}),
        ("injectable_research", "injection/instruction-followed", {"injection/instruction-followed"}),
    ],
)
def test_fix_is_verified(service: AuditService, tmp_path: Path, target: str, rule: str, resolves: set[str]) -> None:
    _, verdicts = fix_target(service, service.project.target(target), tmp_path, options=AuditOptions(timeout_s=30))
    verdict = next(v for v in verdicts if v.proposal.rule_id == rule)
    assert verdict.accepted, verdict.reason
    assert resolves <= {f.rule_id for f in verdict.resolved}
    assert verdict.new_findings == ()
    assert verdict.patched_path is not None
    assert Path(verdict.patched_path).name == f"{target}.hocon"


def test_leak_needs_manual_fix(service: AuditService, tmp_path: Path) -> None:
    _, verdicts = fix_target(
        service, service.project.target("account_leak"), tmp_path, options=AuditOptions(timeout_s=30)
    )
    assert [(v.proposal.manual, v.accepted) for v in verdicts] == [(True, False)]


def test_bad_fix_is_rejected(service: AuditService, tmp_path: Path) -> None:
    from crucible.domain.fix import FixProposal, PatchOp, PatchOpKind
    from crucible.fixes.verify import verify

    spec = service.project.target("fragile_weather")
    scenarios = service.project.scenarios(spec).scenarios
    audit = service.audit_target(spec, AuditOptions(timeout_s=30))
    masked = next(f for f in audit.findings if f.rule_id == "tool/error-masked")
    useless = FixProposal(
        id="fix-useless",
        finding_fingerprint=masked.fingerprint,
        rule_id=masked.rule_id,
        agent="weather_desk",
        rationale="cosmetic",
        ops=(PatchOp(op=PatchOpKind.SET_DESCRIPTION, agent="weather_desk", value="Weather questions for India."),),
    )
    verdict = verify(service, spec, audit, useless, scenarios, tmp_path, AuditOptions(timeout_s=30))
    assert not verdict.accepted
    assert verdict.reason == "target finding still present after the patch"
