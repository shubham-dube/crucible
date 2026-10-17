"""Tool path configuration, including same-named tool packages from different projects."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

from crucible.integrations.neurosan.toolpath import configure_tool_path


def _make_project(root: Path, marker: str) -> Path:
    tools = root / "zz_tools_pkg"
    tools.mkdir(parents=True)
    (tools / "__init__.py").write_text(f"MARKER = {marker!r}\n", encoding="utf-8")
    return tools


def test_switching_projects_evicts_stale_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTHONPATH", "")
    first = _make_project(tmp_path / "a", "first")
    second = _make_project(tmp_path / "b", "second")

    configure_tool_path(first)
    assert importlib.import_module("zz_tools_pkg").MARKER == "first"
    configure_tool_path(second)
    assert importlib.import_module("zz_tools_pkg").MARKER == "second"
    assert os.environ["AGENT_TOOL_PATH"] == str(second.resolve())
    assert os.environ["PYTHONPATH"].split(os.pathsep)[0] == str(second.parent.resolve())
    sys.modules.pop("zz_tools_pkg", None)
