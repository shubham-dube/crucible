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
    # Always move to the front so this project's package shadows same-named ones from earlier projects.
    if parent in sys.path:
        sys.path.remove(parent)
    sys.path.insert(0, parent)
    _evict_stale_package(resolved)
    return resolved


def _evict_stale_package(resolved: Path) -> None:
    """Drop an already-imported package of the same name that lives elsewhere.

    Two projects often both call their tools dir ``coded_tools``; without this, the first one imported wins
    for the rest of the process and the second project's tools cannot be found.
    """
    name = resolved.name
    module = sys.modules.get(name)
    if module is None:
        return
    locations = [str(Path(p).resolve()) for p in getattr(module, "__path__", [])]
    if str(resolved) in locations:
        return
    for key in [k for k in sys.modules if k == name or k.startswith(name + ".")]:
        del sys.modules[key]
