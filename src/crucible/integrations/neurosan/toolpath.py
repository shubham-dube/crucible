"""Make a coded-tools directory resolvable by Neuro-SAN.

Neuro-SAN turns a filesystem ``AGENT_TOOL_PATH`` into a dotted module path relative to the longest matching
``PYTHONPATH`` entry, so the directory's parent must be on ``PYTHONPATH`` *and* importable via ``sys.path``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def configure_tool_path(tool_dir: str | Path) -> Path:
    """Point ``AGENT_TOOL_PATH`` at ``tool_dir`` and make its parent importable. Returns the resolved dir."""
    resolved = Path(tool_dir).resolve()
    parent = str(resolved.parent)
    os.environ["AGENT_TOOL_PATH"] = str(resolved)
    existing = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
    if parent not in existing:
        os.environ["PYTHONPATH"] = os.pathsep.join([parent, *existing])
    if parent not in sys.path:
        sys.path.insert(0, parent)
    return resolved
