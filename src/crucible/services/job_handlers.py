"""Job handlers executed by the worker: audit (gated), agentic audit, fix loop, benchmark."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from crucible.config.project import Project
from crucible.domain.chaos import parse_fault
from crucible.domain.errors import ConfigError
from crucible.domain.findings import Severity
from crucible.domain.trace import RunResult
from crucible.services.audit import AuditOptions, AuditService
from crucible.services.jobs import Emit, Handler, JobKind, JobRecord
from crucible.storage.audits import SqliteAuditRepository
from crucible.storage.run_store import FileRunStore


def build_handlers(home: Path, projects: Callable[[], dict[str, Path]]) -> dict[JobKind, Handler]:
    """Handlers bound to a Crucible home and a project registry."""

    def project_dir(job: JobRecord) -> Path:
        name = str(job.params.get("project", ""))
        registry = projects()
        if name not in registry:
            raise ConfigError(f"unknown project '{name}'; registered: {sorted(registry)}")
        return registry[name]

    def run_event(emit: Emit) -> Callable[[RunResult], None]:
        def on_result(run: RunResult) -> None:
            emit(
                {
                    "type": "run",
                    "target": run.target,
                    "scenario": run.scenario_id,
                    "repetition": run.repetition,
                    "status": run.status.value,
                    "delegations": len(run.delegations()),
                    "duration_s": run.duration_s,
                }
            )

        return on_result

    def audit(job: JobRecord, emit: Emit) -> dict[str, Any]:
        from crucible.services.gate import GateOptions, run_gate

        project = Project.load(project_dir(job))
        service = AuditService(project)
        names = job.params.get("targets") or [t.name for t in project.spec.targets]
        chaos = tuple(job.params.get("chaos") or ())
        for fault in chaos:
            parse_fault(fault)
        options = AuditOptions(
            repetitions=int(job.params.get("repetitions", 1)),
            timeout_s=float(job.params.get("timeout_s", 120.0)),
            chaos=chaos,
        )
        threshold = job.params.get("fail_on", "error")
        result = run_gate(
            service,
            [project.target(n) for n in names],
            options,
            GateOptions(
                threshold=None if threshold == "never" else Severity(threshold),
                baseline=job.params.get("baseline"),
                update_baseline=job.params.get("update_baseline"),
            ),
            SqliteAuditRepository(home),
            FileRunStore(home),
            on_result=run_event(emit),
        )
        return {
            "audit_ids": result.audit_ids,
            "gate_failed": result.failed,
            "regressions": {t: r.to_markdown() for t, r in result.regressions.items()},
            "notes": result.notes,
        }

    def agentic(job: JobRecord, emit: Emit) -> dict[str, Any]:
        from crucible.services.agentic import DEFAULT_REQUEST, run_agentic_audit

        result = run_agentic_audit(
            project_dir(job),
            str(job.params["target"]),
            str(job.params.get("request") or DEFAULT_REQUEST),
            scripted=bool(job.params.get("scripted", False)),
        )
        for hop in result.delegations:
            emit({"type": "handoff", "edge": hop})
        return result.model_dump()

    def fix(job: JobRecord, emit: Emit) -> dict[str, Any]:
        from crucible.execution.runner import new_id
        from crucible.services.fixing import fix_target

        repo = SqliteAuditRepository(home)
        audit = repo.get(str(job.params["audit_id"]))
        project = Project.load(project_dir(job))
        service = AuditService(project)
        _, verdicts = fix_target(service, project.target(audit.target), home / "fixes" / new_id("fix"), baseline=audit)
        for verdict in verdicts:
            emit({"type": "verdict", "proposal": verdict.proposal.id, "accepted": verdict.accepted})
        return {
            "verdicts": [
                {
                    "proposal": v.proposal.model_dump(mode="json"),
                    "accepted": v.accepted,
                    "reason": v.reason,
                    "resolved": [f.rule_id for f in v.resolved],
                    "new_findings": [f.rule_id for f in v.new_findings],
                    "diff": v.diff,
                }
                for v in verdicts
            ]
        }

    def bench(job: JobRecord, emit: Emit) -> dict[str, Any]:
        from crucible.evaluation.benchmark import run_benchmark

        report = run_benchmark(AuditService(Project.load(project_dir(job))), AuditOptions(timeout_s=60.0))
        return {"recall": report.recall, "precision": report.precision, "markdown": report.to_markdown()}

    return {JobKind.AUDIT: audit, JobKind.AGENTIC: agentic, JobKind.FIX: fix, JobKind.BENCH: bench}
