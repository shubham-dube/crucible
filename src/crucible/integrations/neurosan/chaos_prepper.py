"""Inject chaos into Neuro-SAN coded tools through the supported ActivationPrepper extension point.

Registered once per process via ``AGENT_ACTIVATION_PREPPER_CLASSES``. It only claims a coded tool when the active
chaos plan (``crucible.chaos.state``) targets that agent; otherwise Neuro-SAN's stock ClassActivationPrepper runs.
The coded tool is wrapped in a proxy, so Neuro-SAN's own journaling and error handling see a genuine tool failure.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool
from neuro_san.internals.graph.activations.class_activation import ClassActivation
from neuro_san.internals.graph.preppers.class_activation_prepper import ClassActivationPrepper

from crucible.chaos import catalog, state

PREPPER_CLASS = f"{__name__}.CrucibleChaosPrepper"
ENV = "AGENT_ACTIVATION_PREPPER_CLASSES"


def register() -> None:
    """Add the prepper to the env var Neuro-SAN reads when building activation factories (idempotent)."""
    current = os.environ.get(ENV, "").split()
    if PREPPER_CLASS not in current:
        os.environ[ENV] = " ".join([*current, PREPPER_CLASS])


class ChaosToolProxy(CodedTool):  # type: ignore[misc]
    """Applies the selected fault around the real coded tool."""

    def __init__(self, inner: CodedTool, agent: str) -> None:
        self.inner = inner
        self.agent = agent

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        plan = state.current()
        fault = plan.select(self.agent) if plan is not None else None
        if plan is None or fault is None:
            return await self._call_inner(args, sly_data)
        delay = catalog.delay_seconds(fault)
        if delay:
            await asyncio.sleep(delay)
        try:
            note = catalog.before_call(fault, args, sly_data)
        except Exception:
            state.record(plan, f"{fault.id}@{self.agent}: raised")
            raise
        result = await self._call_inner(args, sly_data)
        result, post_note = catalog.after_call(fault, result, plan.marker)
        state.record(plan, f"{fault.id}@{self.agent}" + "".join(f": {n}" for n in (note, post_note) if n))
        return result

    async def _call_inner(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        try:
            return await self.inner.async_invoke(args, sly_data)
        except NotImplementedError:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self.inner.invoke, args, sly_data)


class ChaosClassActivation(ClassActivation):  # type: ignore[misc]
    """ClassActivation that hands Neuro-SAN a fault-injecting proxy instead of the real coded tool."""

    async def attempt_invoke(self, coded_tool: CodedTool, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        agent = str(self.agent_tool_spec.get("name", ""))
        return await super().attempt_invoke(ChaosToolProxy(coded_tool, agent), args, sly_data)


class CrucibleChaosPrepper(ClassActivationPrepper):  # type: ignore[misc]
    """Claims coded tools targeted by the active chaos plan."""

    def is_applicable(self, agent_tool_spec: dict[str, Any]) -> bool:
        plan = state.current()
        if plan is None or not agent_tool_spec or not super().is_applicable(agent_tool_spec):
            return False
        return plan.targets(str(agent_tool_spec.get("name", "")))

    def prepare_activation(
        self,
        name: str,
        agent_tool_spec: dict[str, Any],
        parent_agent_spec: dict[str, Any],
        args: dict[str, Any],
        sly_data: dict[str, Any],
        parent_run_context: Any,
        factory: Any,
        invocation: str,
    ) -> Any:
        use_args = self.merge_args(args, agent_tool_spec)
        return ChaosClassActivation(parent_run_context, factory, use_args, agent_tool_spec, sly_data)
