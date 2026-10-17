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
from crucible.domain.errors import ConfigError
from crucible.domain.findings import Finding
from crucible.domain.scenario import Scenario, ScenarioSource, ScenarioSuite
from crucible.execution.runner import Runner, new_id
from crucible.integrations.neurosan.loader import load_network
from crucible.services.audit import AuditOptions, AuditService, TargetAudit
from crucible.storage.run_store import FileRunStore

_AUDITS: dict[str, TargetAudit] = {}
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
    return _home() / "generated" / f"{target}.yaml"


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
    directory = _home() / "audits"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{audit_id}.json").write_text(audit.model_dump_json(), encoding="utf-8")
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
    path = _home() / "audits" / f"{audit_id}.json"
    if not path.is_file():
        raise ConfigError(f"unknown audit '{audit_id}'")
    audit = TargetAudit.model_validate_json(path.read_text(encoding="utf-8"))
    _AUDITS[audit_id] = audit
    return audit


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
