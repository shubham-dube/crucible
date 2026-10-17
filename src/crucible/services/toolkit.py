"""Framework-free implementations of the tools Crucible's agent network uses.

Every function returns a small JSON-serialisable dict meant for an LLM to read: ids, counts, short messages.
Secrets never appear (judge evidence masks them). Full objects are cached in-process and persisted under
``$CRUCIBLE_HOME`` so later tools (and later CLI commands) can refer to them by id.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from crucible.config import get_settings
from crucible.config.project import Project
from crucible.domain.errors import ConfigError, CrucibleError
from crucible.domain.findings import Finding
from crucible.domain.scenario import Scenario, ScenarioSource, ScenarioSuite
from crucible.execution.runner import Runner, new_id
from crucible.integrations.neurosan.loader import load_network
from crucible.services.audit import AuditOptions, AuditService, TargetAudit
from crucible.storage.audits import SqliteAuditRepository
from crucible.storage.run_store import FileRunStore

_AUDITS: dict[str, TargetAudit] = {}


def repository() -> SqliteAuditRepository:
    """Audit repository for the current $CRUCIBLE_HOME."""
    return SqliteAuditRepository(_home())


_MAX_LISTED = 25


def finding_id(finding: Finding) -> str:
    """Short stable id for a finding within an audit."""
    return hashlib.sha1(f"{finding.fingerprint}|{finding.message}".encode()).hexdigest()[:8]


def _summary(finding: Finding) -> dict[str, Any]:
    return {
        "id": finding_id(finding),
        "rule": finding.rule_id,
        "severity": finding.severity.value,
        "agent": finding.agent,
        "scenario": finding.scenario_id,
        "message": finding.message[:300],
    }


def _home() -> Path:
    return Path(get_settings().home)


def _project(project_dir: str) -> Project:
    project = Project.load(project_dir)
    project.activate()
    return project


def generated_suite_path(target: str) -> Path:
    """Where agent-designed scenarios for a target are stored."""
    from crucible.storage.ids import safe_id

    return _home() / "generated" / f"{safe_id(target, 'target')}.yaml"


def load_generated(target: str) -> ScenarioSuite:
    """Agent-designed scenarios saved so far for ``target``."""
    path = generated_suite_path(target)
    if not path.is_file():
        return ScenarioSuite()
    return ScenarioSuite.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def lint_network(project_dir: str, target: str) -> dict[str, Any]:
    """Static topology findings for a target."""
    from crucible.topology.linter import lint

    project = _project(project_dir)
    result = lint(load_network(project.network_path(project.target(target))))
    return {
        "target": target,
        "counts": {s: sum(1 for f in result.findings if f.severity.value == s) for s in ("error", "warning", "info")},
        "findings": [_summary(f) for f in result.findings[:_MAX_LISTED]],
    }


def coverage_plan(project_dir: str, target: str, timeout_s: float = 60.0) -> dict[str, Any]:
    """Run the current scenarios, report delegation-edge coverage and list uncovered edges with child descriptions."""
    from crucible.integrations.neurosan.direct_adapter import NeuroSanDirectAdapter
    from crucible.scenarios.coverage import CoverageReport, coverage, edges

    project = _project(project_dir)
    spec = project.target(target)
    graph = load_network(project.network_path(spec)).graph
    scenarios = [*project.scenarios(spec).scenarios, *load_generated(target).scenarios]
    if scenarios:
        batch = Runner(NeuroSanDirectAdapter(project.network_path(spec)), timeout_s=timeout_s).run(target, scenarios)
        report = coverage(graph, [batch])
    else:
        report = CoverageReport(edges=tuple(edges(graph)), covered=())
    return {
        "target": target,
        "coverage": round(report.ratio, 3),
        "scenarios": [s.id for s in scenarios],
        "uncovered_edges": [
            {"from": e.src, "to": e.dst, "route": list(e.route), "to_description": graph.nodes[e.dst].description}
            for e in report.uncovered
        ],
        "scenario_schema": {
            "id": "kebab-case unique id",
            "description": "what this tests",
            "interactions": [{"text": "user message", "sly_data": {"optional_private_key": "synthetic value"}}],
            "expect": {"route": ["agents that must be invoked in order"], "must_not_route": [], "answer_contains": []},
        },
    }


def save_scenarios(target: str, scenarios: Any) -> dict[str, Any]:
    """Validate agent-designed scenarios and append the valid ones to the target's generated suite."""
    items = json.loads(scenarios) if isinstance(scenarios, str) else scenarios
    if isinstance(items, dict):
        items = items.get("scenarios", [items])
    if not isinstance(items, list):
        return {"saved": [], "rejected": [{"reason": "expected a JSON list of scenario objects"}]}
    existing = load_generated(target)
    known = {s.id for s in existing.scenarios}
    saved: list[Scenario] = []
    rejected: list[dict[str, str]] = []
    for item in items:
        try:
            scenario = Scenario.model_validate({**item, "source": ScenarioSource.GENERATED.value})
        except (ValidationError, TypeError) as exc:
            rejected.append({"id": str(item.get("id") if isinstance(item, dict) else item), "reason": str(exc)[:300]})
            continue
        if scenario.id in known:
            rejected.append({"id": scenario.id, "reason": "duplicate id"})
            continue
        known.add(scenario.id)
        saved.append(scenario)
    from crucible.scenarios.io import write_suite

    write_suite(ScenarioSuite(scenarios=(*existing.scenarios, *saved)), generated_suite_path(target))
    return {"saved": [s.id for s in saved], "rejected": rejected}


def run_audit(
    project_dir: str,
    target: str,
    include_generated: bool = True,
    chaos: list[str] | None = None,
    repetitions: int = 1,
    timeout_s: float = 60.0,
) -> dict[str, Any]:
    """Run the deterministic audit; cache + persist it; return an id and finding summaries."""
    project = _project(project_dir)
    spec = project.target(target)
    scenarios = list(project.scenarios(spec).scenarios)
    if include_generated:
        scenarios += list(load_generated(target).scenarios)
    options = AuditOptions(repetitions=max(1, int(repetitions)), timeout_s=timeout_s, chaos=tuple(chaos or ()))
    audit = AuditService(project).audit_target(spec, options, scenarios=scenarios)
    audit_id = new_id("audit")
    _AUDITS[audit_id] = audit
    repository().save(audit_id, audit)
    if audit.batch is not None:
        FileRunStore(_home()).save(audit.batch)
    return {
        "audit_id": audit_id,
        "target": target,
        "runs": len(audit.batch.runs) if audit.batch else 0,
        "scenarios": len(scenarios),
        "chaos": list(options.chaos),
        "findings": [_summary(f) for f in audit.findings[:_MAX_LISTED]],
        "total_findings": len(audit.findings),
    }


def get_audit(audit_id: str) -> TargetAudit:
    """Cached or persisted audit by id."""
    if audit_id in _AUDITS:
        return _AUDITS[audit_id]
    try:
        audit = repository().get(audit_id)
    except CrucibleError as exc:
        raise ConfigError(f"unknown audit '{audit_id}'") from exc
    _AUDITS[audit_id] = audit
    return audit


def regression_diff(audit_id: str, label: str = "main") -> dict[str, Any]:
    """Compare an audit with the target's baseline ``label``."""
    from crucible.regression.diff import diff

    audit = get_audit(audit_id)
    baseline_id = repository().baseline(audit.target, label)
    if baseline_id is None:
        return {"audit_id": audit_id, "baseline": None, "note": f"no baseline '{label}' for {audit.target}"}
    result = diff(get_audit(baseline_id), audit)
    return {
        "audit_id": audit_id,
        "baseline": baseline_id,
        "new": [_summary(f) for f in result.new[:_MAX_LISTED]],
        "fixed": [_summary(f) for f in result.fixed[:_MAX_LISTED]],
        "persisting": len(result.persisting),
        "metric_regressions": [m.model_dump() | {"change": round(m.change, 3)} for m in result.metric_regressions],
    }


def finding_evidence(audit_id: str, finding: str) -> dict[str, Any]:
    """Evidence for one finding (by short id), plus the delegation path of the run it came from."""
    audit = get_audit(audit_id)
    match = next((f for f in audit.findings if finding_id(f) == finding), None)
    if match is None:
        return {"error": f"no finding '{finding}' in audit {audit_id}"}
    run = next((r for r in (audit.batch.runs if audit.batch else ()) if r.run_id == match.run_id), None)
    return {
        "finding": _summary(match),
        "remediation": match.remediation,
        "evidence": [{"kind": e.kind, "ref": e.ref, "excerpt": e.excerpt} for e in match.evidence],
        "delegation_path": [f"{a} -> {b}" for a, b in run.delegations()[:20]] if run else [],
        "answer": run.answer[:300] if run else None,
        "chaos": list(run.chaos_fired) if run else [],
    }


def leak_report(audit_id: str) -> dict[str, Any]:
    """All sly_data leak findings of an audit with their (masked) evidence."""
    audit = get_audit(audit_id)
    leaks = [
        f for f in audit.findings if f.rule_id.startswith("leak/") or f.rule_id == "topology/sly-data-passthrough"
    ]
    return {
        "audit_id": audit_id,
        "leaks": [
            {**_summary(f), "evidence": [e.excerpt for e in f.evidence[:6]], "remediation": f.remediation}
            for f in leaks
        ],
    }


def chaos_matrix(project_dir: str, target: str, profiles: list[str] | None = None) -> dict[str, Any]:
    """Run the chaos matrix for a target."""
    from crucible.services.chaos_matrix import run_matrix

    project = _project(project_dir)
    matrix = run_matrix(AuditService(project), project.target(target), profiles, AuditOptions(timeout_s=60.0))
    return {
        "target": target,
        "resilience": round(matrix.resilience, 3),
        "profiles": [
            {"profile": p.profile, "resilient": p.resilient, "new_findings": [_summary(f) for f in p.new_findings[:8]]}
            for p in matrix.profiles
        ],
    }


def render_report(audit_ids: list[str], fmt: str = "markdown", summary: str = "") -> dict[str, Any]:
    """Render audits to a report file under $CRUCIBLE_HOME/reports; returns its path."""
    from crucible.reporting import FindingsReport, get_reporter
    from crucible.reporting.base import TargetFindings

    audits = [get_audit(a) for a in audit_ids]
    report = FindingsReport(
        kind="audit",
        targets=tuple(
            TargetFindings(network=a.target, file=a.network_path, findings=tuple(a.findings)) for a in audits
        ),
    )
    name = "markdown" if fmt in ("markdown", "md") else fmt
    text = get_reporter(name).render(report)
    if name == "markdown" and summary:
        title, _, rest = text.partition("\n")
        text = f"{title}\n\n## Executive summary\n\n{summary}\n{rest}"
    suffix = {"markdown": "md", "json": "json", "sarif": "sarif", "junit": "xml", "table": "txt"}.get(name, "txt")
    directory = _home() / "reports"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{new_id('report')}.{suffix}"
    path.write_text(text, encoding="utf-8")
    return {"path": str(path), "format": name, "targets": [a.target for a in audits]}


_PROPOSALS: dict[str, list[Any]] = {}


def propose_fixes(project_dir: str, audit_id: str) -> dict[str, Any]:
    """Deterministic fix proposals for an audit (cached for verify_fixes)."""
    from crucible.services.fixing import proposals_for

    audit = get_audit(audit_id)
    project = _project(project_dir)
    proposals = proposals_for(AuditService(project), project.target(audit.target), audit)
    _PROPOSALS[audit_id] = proposals
    return {
        "audit_id": audit_id,
        "proposals": [
            {
                "id": p.id,
                "rule": p.rule_id,
                "agent": p.agent,
                "manual": p.manual,
                "rationale": p.rationale,
                "ops": [o.model_dump(mode="json") for o in p.ops],
            }
            for p in proposals
        ],
    }


def verify_fixes(
    project_dir: str, audit_id: str, proposal_ids: list[str] | None = None, ops: Any = None
) -> dict[str, Any]:
    """Verify cached proposals (all, or the given ids) - or one custom proposal from ``ops`` JSON - by re-auditing."""
    from crucible.domain.fix import FixProposal, PatchOp
    from crucible.fixes.verify import verify

    audit = get_audit(audit_id)
    project = _project(project_dir)
    spec = project.target(audit.target)
    candidates = list(_PROPOSALS.get(audit_id, []))
    if ops:
        raw = json.loads(ops) if isinstance(ops, str) else ops
        base = next((p for p in candidates if not proposal_ids or p.id in proposal_ids), None)
        if base is None:
            return {"error": "custom ops need a proposal id to refine (run propose_fixes first)"}
        try:
            parsed = tuple(PatchOp.model_validate(o) for o in raw)
        except (ValidationError, TypeError) as exc:
            return {"error": f"invalid ops: {str(exc)[:300]}"}
        candidates = [FixProposal(**{**base.model_dump(), "id": base.id + "-r", "ops": parsed, "manual": False})]
    elif proposal_ids:
        candidates = [p for p in candidates if p.id in proposal_ids]
    scenarios = [*project.scenarios(spec).scenarios, *load_generated(audit.target).scenarios]
    workdir = _home() / "fixes" / audit_id
    verdicts = [verify(AuditService(project), spec, audit, p, scenarios, workdir) for p in candidates]
    return {
        "audit_id": audit_id,
        "verdicts": [
            {
                "proposal": v.proposal.id,
                "rule": v.proposal.rule_id,
                "agent": v.proposal.agent,
                "accepted": v.accepted,
                "reason": v.reason,
                "resolved": [f.rule_id for f in v.resolved],
                "new_findings": [_summary(f) for f in v.new_findings],
                "patched_network": v.patched_path,
            }
            for v in verdicts
        ],
    }
