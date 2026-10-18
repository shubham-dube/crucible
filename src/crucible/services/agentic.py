"""Run Crucible's own Neuro-SAN agent network (the agentic audit) in-process."""

from __future__ import annotations

import time
from importlib import resources
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from crucible.config import get_settings
from crucible.config.project import Project
from crucible.domain.trace import TokenUsage

DEFAULT_REQUEST = "Audit this agent network thoroughly and tell me whether it is safe to merge."


class AgenticAuditResult(BaseModel):
    """Outcome of an agentic audit session."""

    model_config = ConfigDict(frozen=True)

    answer: str
    audit_ids: tuple[str, ...] = ()
    report_path: str | None = None
    delegations: tuple[str, ...] = Field(default=(), description="Crucible's own agent hand-offs, in order")
    duration_s: float = 0.0
    tokens: TokenUsage = Field(default_factory=TokenUsage, description="Crucible's own agents (not the targets)")


def network_path() -> Path:
    """Path of the bundled Crucible network HOCON."""
    return Path(str(resources.files("crucible.agents") / "registries" / "crucible.hocon"))


def scripted_network_path(home: Path) -> Path:
    """Write the keyless variant: identical topology and tools, ScriptedChatModel instead of a provider.

    Generated from the parsed live config (Neuro-SAN resolves ``include`` against its own registry dir, so a
    static include-based variant is not portable).
    """
    import json

    from crucible.integrations.neurosan.llm_override import override_llm
    from crucible.integrations.neurosan.loader import load_config

    scripted = {
        "class": "crucible.integrations.neurosan.scripted_llm.ScriptedChatModel",
        "script_path": str(script_path()),
    }
    config = override_llm(load_config(network_path()), scripted)
    target = home / "agents" / "crucible_scripted.hocon"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(config, indent=1), encoding="utf-8")
    return target


def agent_network_path(home: Path, scripted: bool = False) -> Path:
    """The network to run: keyless variant, an LLM-overridden copy (``CRUCIBLE_AGENT_LLM``), or the bundled one."""
    if scripted:
        return scripted_network_path(home)
    agent_llm = get_settings().agent_llm
    if agent_llm:
        from crucible.integrations.neurosan.llm_override import parse_llm_spec, write_llm_variant

        return write_llm_variant(network_path(), parse_llm_spec(agent_llm), home / "llm_variants")
    return network_path()


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
    from crucible.execution.budget import default_guard

    budget = default_guard()
    budget.ensure()
    path = agent_network_path(Path(get_settings().home), scripted)
    tokens = TokenUsage()
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
        if "total_tokens" in structure and len(message.get("origin") or []) <= 1:  # front man's running total
            tokens = TokenUsage(
                total=int(structure.get("total_tokens") or 0),
                prompt=int(structure.get("prompt_tokens") or 0),
                completion=int(structure.get("completion_tokens") or 0),
                cost_usd=float(structure.get("total_cost") or 0.0),
            )
        if message.get("type") == 101:
            answer = str(message.get("text") or "")
            returned = message.get("sly_data") or {}
    budget.charge("agentic", target, tokens)
    return AgenticAuditResult(
        answer=answer,
        tokens=tokens,
        audit_ids=tuple(returned.get(AUDITS_KEY) or ()),
        report_path=returned.get(REPORT_KEY),
        delegations=tuple(delegations),
        duration_s=round(time.monotonic() - start, 2),
    )
