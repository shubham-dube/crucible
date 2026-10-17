"""crucible.yaml loading."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from crucible.config.project import Project
from crucible.domain.errors import ConfigError


def _write(tmp: Path, text: str) -> Path:
    (tmp / "crucible.yaml").write_text(text, encoding="utf-8")
    return tmp


def test_load_and_resolve(tmp_path: Path) -> None:
    (tmp_path / "s.yaml").write_text("scenarios: [{id: a, interactions: [{text: hi}]}]\n", encoding="utf-8")
    project = Project.load(
        _write(tmp_path, "targets: [{name: t, network: nets/t.hocon, scenarios: s.yaml}]\nscript_dir: scripts\n")
    )
    target = project.target("t")
    assert project.network_path(target) == (tmp_path / "nets" / "t.hocon").resolve()
    assert project.scenarios(target).scenarios[0].id == "a"
    assert project.expected(target) is None


def test_unknown_target_and_missing_file(tmp_path: Path) -> None:
    project = Project.load(_write(tmp_path, "targets: []\n"))
    with pytest.raises(ConfigError, match="unknown target"):
        project.target("nope")
    with pytest.raises(ConfigError, match="not found"):
        Project.load(tmp_path / "missing")


def test_invalid_yaml_key(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="invalid"):
        Project.load(_write(tmp_path, "bogus: 1\n"))


def test_activate_sets_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "tools").mkdir()
    monkeypatch.delenv("CRUCIBLE_SCRIPT_DIR", raising=False)
    monkeypatch.setenv("PYTHONPATH", "")
    project = Project.load(_write(tmp_path, "coded_tools: tools\nscript_dir: scripts\nenv: {FOO_X: bar}\n"))
    project.activate()
    assert os.environ["AGENT_TOOL_PATH"] == str((tmp_path / "tools").resolve())
    assert os.environ["CRUCIBLE_SCRIPT_DIR"] == str((tmp_path / "scripts").resolve())
    assert os.environ["FOO_X"] == "bar"
    monkeypatch.delenv("FOO_X")
