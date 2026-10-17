"""Run Crucible's own Neuro-SAN agent network (the agentic audit) in-process."""

from __future__ import annotations

import time
from importlib import resources
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from crucible.config import get_settings
from crucible.config.project import Project

DEFAULT_REQUEST = "Audit this agent network thoroughly and tell me whether it is safe to merge."


class AgenticAuditResult(BaseModel):
    """Outcome of an agentic audit session."""

    model_config = ConfigDict(frozen=True)

    answer: str
    audit_ids: tuple[str, ...] = ()
    report_path: str | None = None
    delegations: tuple[str, ...] = Field(default=(), description="Crucible's own agent hand-offs, in order")
    duration_s: float = 0.0


def network_path() -> Path:
    """Path of the bundled Crucible network HOCON."""
    return Path(str(resources.files("crucible.agents") / "registries" / "crucible.hocon"))


def scripted_network_path(home: Path) -> Path:
    """Write the keyless variant: identical topology and tools, ScriptedChatModel instead of a provider.

    Generated from the parsed live config (Neuro-SAN resolves ``include`` against its own registry dir, so a
    static include-based variant is not portable).
    """
    import json

    from crucible.integrations.neurosan.loader import load_config

    config = load_config(network_path())
    scripted = {
        "class": "crucible.integrations.neurosan.scripted_llm.ScriptedChatModel",
        "script_path": str(script_path()),
    }
    config["llm_config"] = scripted
    for spec in config.get("tools") or []:
        if isinstance(spec, dict) and "llm_config" in spec:  # Neuro-SAN's filters copy llm_config into each agent
            spec["llm_config"] = dict(scripted)
    target = home / "agents" / "crucible_scripted.hocon"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(config, indent=1), encoding="utf-8")
    return target


def script_path() -> Path:
    """Bundled script for the keyless variant."""
    return Path(str(resources.files("crucible.agents") / "scripts" / "crucible_scripted.yaml"))


def run_agentic_audit(
    project_dir: str | Path, target: str, request: str = DEFAULT_REQUEST, scripted: bool = False
) -> AgenticAuditResult:
    """Let the conductor plan and run the audit through its specialists."""
    from neuro_san.client.agent_session_factory import AgentSessionFactory
    from neuro_san.client.streaming_input_processor import StreamingInputProcessor

    from crucible.integrations.neurosan import chaos_prepper
    from crucible.integrations.neurosan.agent_tools import AUDITS_KEY, REPORT_KEY

    project = Project.load(project_dir)
    project.activate()  # tool paths must be valid before any activation factory is built
    project.target(target)  # fail fast on unknown target
    chaos_prepper.register()
    path = scripted_network_path(Path(get_settings().home)) if scripted else network_path()
    start = time.monotonic()
    session = AgentSessionFactory().create_session(
        "direct", str(path), use_direct=True, metadata={"user_id": "crucible"}
    )
    session.reset()
    sip = StreamingInputProcessor(session=session)
    sly = {"project_dir": str(project.root), "target": target}
    chat_request = sip.formulate_chat_request(request, sly, None, {"chat_filter_type": "MAXIMAL"})
    answer = ""
    returned: dict[str, Any] = {}
    delegations: list[str] = []
    for response in session.streaming_chat(chat_request):
        message: dict[str, Any] = response.get("response") or {}
        raw_structure = message.get("structure")
        structure: dict[str, Any] = raw_structure if isinstance(raw_structure, dict) else {}
        if structure.get("invoking_start"):
            caller = (message.get("origin") or [{}])[-1].get("tool")
            delegations.append(f"{caller} -> {structure.get('invoked_agent_name')}")
        if message.get("type") == 101:
            answer = str(message.get("text") or "")
            returned = message.get("sly_data") or {}
    return AgenticAuditResult(
        answer=answer,
        audit_ids=tuple(returned.get(AUDITS_KEY) or ()),
        report_path=returned.get(REPORT_KEY),
        delegations=tuple(delegations),
        duration_s=round(time.monotonic() - start, 2),
    )
