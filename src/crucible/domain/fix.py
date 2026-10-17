"""Fix proposals: structured patches to a network config, and the verifier's verdict."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from crucible.domain.findings import Finding


class PatchOpKind(StrEnum):
    """Supported config edits."""

    APPEND_INSTRUCTIONS = "append_instructions"
    SET_INSTRUCTIONS = "set_instructions"
    SET_DESCRIPTION = "set_description"
    SET_TOP_LEVEL = "set_top_level"
    REMOVE_TOOL = "remove_tool"
    SET_ALLOW_KEYS = "set_allow_keys"


class PatchOp(BaseModel):
    """One edit. ``agent`` is required for agent-level ops; ``key`` names the tool / top-level key / direction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    op: PatchOpKind
    agent: str | None = None
    key: str | None = None
    value: Any = None


class FixProposal(BaseModel):
    """A candidate fix for one finding."""

    model_config = ConfigDict(frozen=True)

    id: str
    finding_fingerprint: str
    rule_id: str
    agent: str | None = None
    rationale: str
    ops: tuple[PatchOp, ...] = ()
    manual: bool = Field(default=False, description="needs a code change outside the network config")


class FixVerdict(BaseModel):
    """Result of verifying a proposal by re-running the audit on a patched copy."""

    model_config = ConfigDict(frozen=True)

    proposal: FixProposal
    accepted: bool
    target_fixed: bool
    resolved: tuple[Finding, ...] = ()
    new_findings: tuple[Finding, ...] = ()
    diff: str = ""
    patched_path: str | None = None
    reason: str = ""
