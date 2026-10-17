"""Apply patch ops to a parsed network config (pure) and write a patched copy."""

from __future__ import annotations

import copy
import difflib
import json
from pathlib import Path
from typing import Any

from crucible.domain.errors import ConfigError
from crucible.domain.fix import PatchOp, PatchOpKind

_DIRECTIONS = ("to_downstream", "from_downstream", "to_upstream", "to_tracing")


def _agent(config: dict[str, Any], name: str | None) -> dict[str, Any]:
    for spec in config.get("tools") or []:
        if isinstance(spec, dict) and spec.get("name") == name:
            return spec
    raise ConfigError(f"patch refers to unknown agent '{name}'")


def apply_ops(config: dict[str, Any], ops: tuple[PatchOp, ...] | list[PatchOp]) -> dict[str, Any]:
    """Return a patched deep copy of ``config``."""
    out = copy.deepcopy(config)
    for op in ops:
        if op.op is PatchOpKind.SET_TOP_LEVEL:
            if not op.key:
                raise ConfigError("set_top_level needs a key")
            out[op.key] = op.value
            for spec in out.get("tools") or []:  # Neuro-SAN's filters copy some top-level keys into agents
                if isinstance(spec, dict) and op.key in spec:
                    spec[op.key] = op.value
            continue
        spec = _agent(out, op.agent)
        if op.op is PatchOpKind.APPEND_INSTRUCTIONS:
            spec["instructions"] = (str(spec.get("instructions", "")).rstrip() + "\n" + str(op.value)).strip()
        elif op.op is PatchOpKind.SET_INSTRUCTIONS:
            spec["instructions"] = str(op.value)
        elif op.op is PatchOpKind.SET_DESCRIPTION:
            spec.setdefault("function", {})["description"] = str(op.value)
        elif op.op is PatchOpKind.REMOVE_TOOL:
            tools = list(spec.get("tools") or [])
            if op.key not in tools:
                raise ConfigError(f"agent '{op.agent}' has no tool '{op.key}'")
            spec["tools"] = [t for t in tools if t != op.key]
        elif op.op is PatchOpKind.SET_ALLOW_KEYS:
            if op.key not in _DIRECTIONS:
                raise ConfigError(f"allow direction must be one of {_DIRECTIONS}")
            spec.setdefault("allow", {}).setdefault(op.key, {})["sly_data"] = list(op.value or [])
    return out


def config_diff(before: dict[str, Any], after: dict[str, Any], name: str) -> str:
    """Unified diff of the pretty-printed configs."""
    a = json.dumps(before, indent=2, sort_keys=True, default=str).splitlines(keepends=True)
    b = json.dumps(after, indent=2, sort_keys=True, default=str).splitlines(keepends=True)
    return "".join(difflib.unified_diff(a, b, fromfile=f"{name} (current)", tofile=f"{name} (fixed)", n=2))


def write_patched(config: dict[str, Any], stem: str, directory: Path) -> Path:
    """Write the patched network as ``<directory>/<stem>.hocon`` (JSON is valid HOCON).

    The stem must match the original: Neuro-SAN resolves coded tools under ``AGENT_TOOL_PATH/<network name>/``.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem}.hocon"
    path.write_text(json.dumps(config, indent=1, default=str), encoding="utf-8")
    return path
