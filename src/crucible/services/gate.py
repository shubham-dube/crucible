"""Merge gate: audit targets, compare with baselines, decide pass/fail (shared by CLI, Action and API)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from crucible.config.project import TargetSpec
from crucible.domain.audit import TargetAudit
from crucible.domain.errors import CrucibleError
from crucible.domain.findings import Finding, Severity
from crucible.domain.trace import SpanKind
from crucible.execution.runner import new_id
from crucible.regression.diff import RegressionDiff, diff
from crucible.services.audit import AuditOptions, AuditService
from crucible.storage.audits import AuditRepository
from crucible.storage.run_store import FileRunStore

SUMMARY_MARKER = "<!-- crucible-report -->"


def load_baseline_file(path: Path) -> dict[str, TargetAudit]:
    """Read a portable baseline file: {"version": 1, "audits": {target: TargetAudit}}."""
    if not path.is_file():
        raise CrucibleError(f"baseline file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return {name: TargetAudit.model_validate(audit) for name, audit in (data.get("audits") or {}).items()}


def write_baseline_file(path: Path, audits: dict[str, TargetAudit]) -> None:
    """Compact baseline (findings + delegation spans/metrics, no prompts) for committing or CI artifacts."""
    compact = {}
    for name, audit in audits.items():
        batch = audit.batch
        if batch is not None:
            runs = tuple(
                r.model_copy(
                    update={"spans": tuple(s for s in r.spans if s.kind is SpanKind.DELEGATION), "llm_calls": ()}
                )
                for r in batch.runs
            )
            batch = batch.model_copy(update={"runs": runs})
        compact[name] = json.loads(audit.model_copy(update={"batch": batch}).model_dump_json())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "audits": compact}, indent=1), encoding="utf-8")


def fails(findings: Sequence[Finding], threshold: Severity | None) -> bool:
    """Any finding at/above ``threshold``."""
    return threshold is not None and any(f.severity.rank >= threshold.rank for f in findings)


@dataclass
class GateResult:
    """Outcome of a gated audit run."""

    audits: dict[str, TargetAudit] = field(default_factory=dict)
    audit_ids: dict[str, str] = field(default_factory=dict)
    regressions: dict[str, RegressionDiff] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    failed: bool = False


@dataclass
class GateOptions:
    """How to gate."""

    threshold: Severity | None = Severity.ERROR
    baseline: str | None = None  # label or path to a .json baseline file
    update_baseline: str | None = None
    save: bool = True


def run_gate(
    service: AuditService,
    specs: Sequence[TargetSpec],
    audit_options: AuditOptions,
    gate: GateOptions,
    repo: AuditRepository,
    store: FileRunStore,
) -> GateResult:
    """Audit each target; with a baseline only NEW findings (or metric regressions) fail the gate."""
    result = GateResult()
    file_baselines = (
        load_baseline_file(Path(gate.baseline)) if gate.baseline and gate.baseline.endswith(".json") else None
    )
    for spec in specs:
        audit = service.audit_target(spec, audit_options)
        audit_id = new_id("audit")
        result.audits[spec.name] = audit
        if gate.save:
            repo.save(audit_id, audit)
            if audit.batch is not None:
                store.save(audit.batch)
            result.audit_ids[spec.name] = audit_id
            result.notes.append(f"{spec.name}: audit {audit_id}")
        base = _baseline_for(spec.name, gate.baseline, file_baselines, repo)
        if base is not None:
            regression = diff(base, audit)
            result.regressions[spec.name] = regression
            result.failed = result.failed or regression.fails(gate.threshold)
        else:
            if gate.baseline:
                result.notes.append(f"{spec.name}: no baseline '{gate.baseline}' for this target; gating on all")
            result.failed = result.failed or fails(audit.findings, gate.threshold)
        if gate.update_baseline and gate.save:
            repo.set_baseline(spec.name, gate.update_baseline, audit_id)
            result.notes.append(f"{spec.name}: baseline '{gate.update_baseline}' -> {audit_id}")
    return result


def _baseline_for(
    target: str, baseline: str | None, files: dict[str, TargetAudit] | None, repo: AuditRepository
) -> TargetAudit | None:
    if files is not None:
        return files.get(target)
    base_id = repo.baseline(target, baseline) if baseline else None
    return repo.get(base_id) if base_id else None


def summary_markdown(result: GateResult, findings_markdown: str) -> str:
    """PR comment / step summary body."""
    verdict = "❌ Crucible gate failed" if result.failed else "✅ Crucible gate passed"
    parts = [
        SUMMARY_MARKER,
        f"## {verdict}",
        *(r.to_markdown() for r in result.regressions.values()),
        findings_markdown,
    ]
    return "\n\n".join(parts)
