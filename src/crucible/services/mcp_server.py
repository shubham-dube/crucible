"""Serve Crucible's own agent network as an MCP tool through Neuro-SAN's server."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from crucible.config.project import Project
from crucible.services.agentic import agent_network_path

TOOL_NAME = "crucible"


def prepare(home: Path, project_dir: Path, target: str, scripted: bool) -> dict[str, str]:
    """Write a registry + manifest for the Crucible network and return the server environment."""
    from crucible.integrations.neurosan.loader import load_config

    project = Project.load(project_dir)
    project.target(target)  # fail fast
    project.activate()
    registry = home / "mcp" / "registries"
    registry.mkdir(parents=True, exist_ok=True)
    source = agent_network_path(home, scripted)
    config = load_config(source)
    (registry / f"{TOOL_NAME}.hocon").write_text(json.dumps(config, indent=1), encoding="utf-8")
    manifest = registry / "manifest.hocon"
    manifest.write_text(
        json.dumps({f"{TOOL_NAME}.hocon": {"serve": True, "public": True, "mcp": True}}, indent=1), encoding="utf-8"
    )
    from crucible.integrations.neurosan import chaos_prepper

    chaos_prepper.register()
    env = dict(os.environ)
    env.update(
        {
            "AGENT_MANIFEST_FILE": str(manifest),
            "AGENT_MCP_ENABLE": "true",
            "CRUCIBLE_PROJECT_DIR": str(project.root),
            "CRUCIBLE_TARGET": target,
            "CRUCIBLE_HOME": str(home),
        }
    )
    return env


def server_command(port: int) -> list[str]:
    """Neuro-SAN server invocation."""
    return [sys.executable, "-m", "neuro_san.service.main_loop.server_main_loop", "--http_port", str(port)]
