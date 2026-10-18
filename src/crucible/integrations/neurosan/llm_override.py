"""Run any network on a different LLM by rewriting its ``llm_config`` into a parsed copy.

Neuro-SAN's filter chain copies the top-level ``llm_config`` into every agent spec, so per-agent configs are replaced
too. The copy is plain JSON (valid HOCON) written from the *resolved* config, so includes stay portable.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from crucible.domain.errors import ConfigError

PROVIDER_CLASSES = {"gemini": "gemini", "google": "gemini", "anthropic": "anthropic", "openai": "openai"}


def _coerce(value: str) -> Any:
    for cast in (int, float):
        try:
            return cast(value)
        except ValueError:
            continue
    return {"true": True, "false": False}.get(value.lower(), value)


def parse_llm_spec(spec: str) -> dict[str, Any]:
    """``provider:model[,key=value...]`` or ``model[,key=value...]`` -> a Neuro-SAN ``llm_config``.

    Example: ``gemini:gemini-3.5-flash-lite,max_tokens=1024``.
    """
    head, *params = [part.strip() for part in spec.split(",")]
    if not head:
        raise ConfigError(f"empty LLM spec: {spec!r}")
    llm: dict[str, Any] = {}
    provider, sep, model = head.partition(":")
    if sep:
        if provider not in PROVIDER_CLASSES or not model:
            raise ConfigError(f"unknown LLM provider in {spec!r}; use one of {sorted(PROVIDER_CLASSES)}")
        llm["class"] = PROVIDER_CLASSES[provider]
        llm["model_name"] = model
    else:
        llm["model_name"] = head
    for param in params:
        key, eq, value = param.partition("=")
        if not eq or not key:
            raise ConfigError(f"bad LLM parameter {param!r} in {spec!r}; expected key=value")
        llm[key.strip()] = _coerce(value.strip())
    return llm


def override_llm(config: dict[str, Any], llm: dict[str, Any]) -> dict[str, Any]:
    """Copy of ``config`` with the top-level and every per-agent ``llm_config`` replaced by ``llm``."""
    out = copy.deepcopy(config)
    out["llm_config"] = dict(llm)
    for spec in out.get("tools") or []:
        if isinstance(spec, dict) and "llm_config" in spec:
            spec["llm_config"] = dict(llm)
    return out


def variant_dir(out_root: Path, source: Path, llm: dict[str, Any]) -> Path:
    """Deterministic directory for a (source, llm) pair, so repeated runs reuse one file."""
    key = json.dumps({"source": str(source.resolve()), "llm": llm}, sort_keys=True)
    return out_root / hashlib.sha256(key.encode()).hexdigest()[:12]


def write_llm_variant(source: Path, llm: dict[str, Any], out_root: Path) -> Path:
    """Write ``source`` re-pointed at ``llm``; the file keeps the original stem (agent name)."""
    from crucible.integrations.neurosan.loader import load_config

    config = override_llm(load_config(source), llm)
    target = variant_dir(out_root, source, llm) / f"{source.stem}.hocon"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(config, indent=1), encoding="utf-8")
    return target
