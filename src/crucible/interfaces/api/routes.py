"""``/v1`` routers: projects, audits, jobs."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from crucible.config.project import Project
from crucible.interfaces.api.state import AppState, get_state
from crucible.services.jobs import JobKind, JobRecord, JobStatus
from crucible.services.masking import mask_run

State = Annotated[AppState, Depends(get_state)]


class AuditRequest(BaseModel):
    """Start a (gated) audit, or an agentic audit of one target."""

    project: str
    targets: list[str] = Field(default_factory=list, max_length=50)
    repetitions: int = Field(default=1, ge=1, le=20)
    chaos: list[str] = Field(default_factory=list, max_length=20)
    baseline: str | None = None
    update_baseline: str | None = None
    fail_on: Literal["error", "warning", "never"] = "error"
    timeout_s: float = Field(default=120.0, gt=0, le=3600)
    agentic: bool = False
    scripted: bool = False
    request: str | None = Field(default=None, max_length=4000)


class ProjectRequest(BaseModel):
    """A job scoped to one registered project."""

    project: str


projects = APIRouter(tags=["projects"])
audits = APIRouter(tags=["audits"])
jobs = APIRouter(tags=["jobs"])


@projects.get("/projects")
def list_projects(state: State) -> list[dict[str, Any]]:
    """Registered projects and their targets."""
    out = []
    for name, path in state.settings.project_map().items():
        spec = Project.load(path).spec
        out.append({"name": name, "targets": [{"name": t.name, "description": t.description} for t in spec.targets]})
    return out


@projects.get("/projects/{name}/targets/{target}/graph")
def target_graph(name: str, target: str, state: State) -> dict[str, Any]:
    """Nodes and delegation edges of a target network."""
    from crucible.integrations.neurosan.loader import load_network

    project = state.project(name)
    graph = load_network(project.network_path(project.target(target))).graph
    return {
        "name": graph.name,
        "front_man": graph.front_man,
        "nodes": [
            {"id": n.name, "kind": n.kind.value, "description": n.description[:300], "class": n.class_ref}
            for n in graph.nodes.values()
        ],
        "edges": [{"source": e.src, "target": e.dst, "kind": e.kind.value} for e in graph.edges],
        "limits": graph.limits.model_dump(),
    }


@projects.get("/projects/{name}/targets/{target}/lint")
def target_lint(name: str, target: str, state: State) -> dict[str, Any]:
    """Static lint findings."""
    from crucible.integrations.neurosan.loader import load_network
    from crucible.topology.linter import lint

    project = state.project(name)
    return lint(load_network(project.network_path(project.target(target)))).model_dump(mode="json")


@audits.get("/audits")
def list_audits(state: State, target: str | None = None, limit: int = Query(50, ge=1, le=500)) -> list[dict[str, Any]]:
    """Recent audits, newest first."""
    return [r.model_dump() for r in state.repo.list(target, limit)]


@audits.get("/audits/{audit_id}")
def get_audit(audit_id: str, state: State) -> dict[str, Any]:
    """Findings and per-run summaries (secrets masked)."""
    audit = state.repo.get(audit_id)
    runs = audit.batch.runs if audit.batch else ()
    return {
        "id": audit_id,
        "target": audit.target,
        "network_path": audit.network_path,
        "findings": [f.model_dump(mode="json") for f in audit.findings],
        "runs": [
            {
                "run_id": r.run_id,
                "scenario_id": r.scenario_id,
                "repetition": r.repetition,
                "status": r.status.value,
                "duration_s": r.duration_s,
                "tokens": r.tokens.total,
                "delegations": len(r.delegations()),
                "chaos": list(r.chaos_fired),
                "answer": mask_run(r).answer[:500],
            }
            for r in runs
        ],
    }


@audits.get("/audits/{audit_id}/runs/{run_id}")
def get_run(audit_id: str, run_id: str, state: State) -> dict[str, Any]:
    """Full trace of one run (secrets masked)."""
    audit = state.repo.get(audit_id)
    match = next((r for r in (audit.batch.runs if audit.batch else ()) if r.run_id == run_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"unknown run '{run_id}'")
    return mask_run(match).model_dump(mode="json")


@audits.get("/audits/{audit_id}/diff")
def audit_diff(audit_id: str, state: State, against: str = "main") -> dict[str, Any]:
    """Regression diff against a baseline label or audit id."""
    from crucible.regression.diff import diff

    current = state.repo.get(audit_id)
    base_id = state.repo.baseline(current.target, against) or against
    result = diff(state.repo.get(base_id), current)
    return {"baseline": base_id, "markdown": result.to_markdown(), **result.model_dump(mode="json")}


@audits.put("/baselines/{target}/{label}")
def set_baseline(target: str, label: str, audit_id: str, state: State) -> dict[str, str]:
    """Point a baseline label at an audit."""
    state.repo.set_baseline(target, label, audit_id)
    return {"target": target, "label": label, "audit_id": audit_id}


@audits.post("/audits", status_code=202)
def start_audit(body: AuditRequest, state: State) -> JobRecord:
    """Queue an audit job."""
    state.project(body.project)
    if body.agentic:
        if len(body.targets) != 1:
            raise HTTPException(status_code=422, detail="agentic audits take exactly one target")
        params = {
            "project": body.project,
            "target": body.targets[0],
            "scripted": body.scripted,
            "request": body.request,
        }
        return state.jobs.submit(JobKind.AGENTIC, params)
    return state.jobs.submit(JobKind.AUDIT, body.model_dump(exclude={"agentic", "scripted", "request"}))


@audits.post("/audits/{audit_id}/fix", status_code=202)
def start_fix(audit_id: str, body: ProjectRequest, state: State) -> JobRecord:
    """Queue the verified fix loop for an audit."""
    state.repo.get(audit_id)
    state.project(body.project)
    return state.jobs.submit(JobKind.FIX, {"project": body.project, "audit_id": audit_id})


@audits.post("/bench", status_code=202)
def start_bench(body: ProjectRequest, state: State) -> JobRecord:
    """Queue a benchmark run."""
    state.project(body.project)
    return state.jobs.submit(JobKind.BENCH, {"project": body.project})


@jobs.get("/jobs")
def list_jobs(state: State, limit: int = Query(50, ge=1, le=500)) -> list[JobRecord]:
    """Recent jobs."""
    return state.store.list(limit)


@jobs.get("/jobs/{job_id}")
def get_job(job_id: str, state: State) -> JobRecord:
    """One job."""
    job = state.store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown job '{job_id}'")
    return job


@jobs.get("/jobs/{job_id}/events")
async def job_events(job_id: str, state: State, poll_s: float = Query(0.5, ge=0.05, le=5.0)) -> StreamingResponse:
    """Server-sent events with job progress until it finishes."""
    if state.store.get(job_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown job '{job_id}'")

    async def stream() -> AsyncIterator[str]:
        sent = 0
        while True:
            events = state.jobs.events(job_id, sent)
            for event in events:
                yield f"data: {json.dumps(event, default=str)}\n\n"
            sent += len(events)
            job = state.store.get(job_id)
            if job is not None and job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED) and not events:
                yield f"event: end\ndata: {json.dumps({'status': job.status.value})}\n\n"
                return
            await asyncio.sleep(poll_s)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
