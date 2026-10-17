"""Neuro-SAN coded tools used by Crucible's own agent network.

Thin adapters: read ``project_dir``/``target`` from sly_data (so the LLM never handles paths), call
``crucible.services.toolkit`` and return compact JSON. Audit ids are recorded in sly_data for later tools.
"""

from __future__ import annotations

import json
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from crucible.domain.errors import CrucibleError
from crucible.services import toolkit

AUDITS_KEY = "crucible_audits"
REPORT_KEY = "crucible_report"


def _ctx(args: dict[str, Any], sly_data: dict[str, Any]) -> tuple[str, str]:
    project_dir = sly_data.get("project_dir")
    target = args.get("target") or sly_data.get("target")
    if not project_dir or not target:
        raise CrucibleError("sly_data must provide 'project_dir' and a 'target' (or pass target)")
    return str(project_dir), str(target)


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=str)


class _Tool(CodedTool):  # type: ignore[misc]
    """Shared error handling: tool errors come back as JSON the agent can reason about."""

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        try:
            return _dump(self.run(args, sly_data))
        except CrucibleError as exc:
            return _dump({"error": str(exc)})

    def run(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class LintNetwork(_Tool):
    """Static topology analysis."""

    def run(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        return toolkit.lint_network(*_ctx(args, sly_data))


class CoveragePlan(_Tool):
    """Delegation-edge coverage and uncovered edges."""

    def run(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        return toolkit.coverage_plan(*_ctx(args, sly_data))


class SaveScenarios(_Tool):
    """Validate and store agent-designed scenarios."""

    def run(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        _, target = _ctx(args, sly_data)
        return toolkit.save_scenarios(target, args.get("scenarios", "[]"))


class RunAudit(_Tool):
    """Execute + judge; remembers the audit id in sly_data."""

    def run(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        project_dir, target = _ctx(args, sly_data)
        chaos = args.get("chaos") or []
        if isinstance(chaos, str):
            chaos = [c.strip() for c in chaos.split(",") if c.strip()]
        result = toolkit.run_audit(
            project_dir,
            target,
            include_generated=bool(args.get("include_generated", True)),
            chaos=list(chaos),
            repetitions=int(args.get("repetitions", 1) or 1),
        )
        sly_data.setdefault(AUDITS_KEY, []).append(result["audit_id"])
        return result


class FindingEvidence(_Tool):
    """Evidence for a finding id."""

    def run(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        audit_id = args.get("audit_id") or (sly_data.get(AUDITS_KEY) or [""])[-1]
        return toolkit.finding_evidence(str(audit_id), str(args.get("finding_id", "")))


class LeakReport(_Tool):
    """Leak findings for the latest (or given) audit."""

    def run(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        audit_id = args.get("audit_id") or (sly_data.get(AUDITS_KEY) or [""])[-1]
        return toolkit.leak_report(str(audit_id))


class ChaosMatrix(_Tool):
    """Chaos matrix for the target."""

    def run(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        project_dir, target = _ctx(args, sly_data)
        profiles = args.get("profiles")
        if isinstance(profiles, str):
            profiles = [p.strip() for p in profiles.split(",") if p.strip()]
        return toolkit.chaos_matrix(project_dir, target, profiles or None)


class RenderReport(_Tool):
    """Write the report for all audits of this session."""

    def run(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        audit_ids = list(sly_data.get(AUDITS_KEY) or [])
        if not audit_ids:
            return {"error": "no audits have been run yet"}
        result = toolkit.render_report(audit_ids, str(args.get("format", "markdown")), str(args.get("summary", "")))
        sly_data[REPORT_KEY] = result["path"]
        return result
