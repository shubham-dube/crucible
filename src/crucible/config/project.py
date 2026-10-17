"""``crucible.yaml``: describes a project's networks, coded tools and scenarios."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from crucible.domain.errors import ConfigError
from crucible.domain.scenario import ExpectedFindings, ScenarioSuite

PROJECT_FILE = "crucible.yaml"


class TargetSpec(BaseModel):
    """One network under test. Paths are relative to the project file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    network: str
    scenarios: str | None = None
    expected: str | None = None
    description: str = ""


class ProjectSpec(BaseModel):
    """The parsed ``crucible.yaml``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = 1
    coded_tools: str | None = Field(default=None, description="AGENT_TOOL_PATH directory")
    script_dir: str | None = Field(default=None, description="directory for ScriptedChatModel scripts")
    env: dict[str, str] = Field(default_factory=dict)
    targets: tuple[TargetSpec, ...] = ()


class Project:
    """A loaded project with path resolution helpers."""

    def __init__(self, spec: ProjectSpec, root: Path) -> None:
        self.spec = spec
        self.root = root

    @classmethod
    def load(cls, path: str | Path) -> Project:
        """Load ``crucible.yaml`` from a file path or a directory containing it."""
        file = Path(path)
        if file.is_dir():
            file = file / PROJECT_FILE
        if not file.is_file():
            raise ConfigError(f"project file not found: {file}")
        try:
            data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
            spec = ProjectSpec.model_validate(data)
        except (yaml.YAMLError, ValueError) as exc:
            raise ConfigError(f"invalid {file}: {exc}") from exc
        return cls(spec, file.resolve().parent)

    def resolve(self, relative: str) -> Path:
        """Resolve a path relative to the project root."""
        return (self.root / relative).resolve()

    def target(self, name: str) -> TargetSpec:
        """Find a target by name."""
        for target in self.spec.targets:
            if target.name == name:
                return target
        raise ConfigError(f"unknown target '{name}'; known: {[t.name for t in self.spec.targets]}")

    def network_path(self, target: TargetSpec) -> Path:
        """Absolute path of a target's HOCON."""
        return self.resolve(target.network)

    def scenarios(self, target: TargetSpec) -> ScenarioSuite:
        """Load a target's hand-written scenarios (empty suite if none)."""
        if not target.scenarios:
            return ScenarioSuite()
        return ScenarioSuite.model_validate(_read_yaml(self.resolve(target.scenarios)))

    def expected(self, target: TargetSpec) -> ExpectedFindings | None:
        """Load a target's expected findings (benchmark targets only)."""
        if not target.expected:
            return None
        return ExpectedFindings.model_validate(_read_yaml(self.resolve(target.expected)))

    def activate(self) -> None:
        """Export the environment Neuro-SAN needs to run this project's networks in-process."""
        from crucible.integrations.neurosan.toolpath import configure_tool_path

        if self.spec.coded_tools:
            configure_tool_path(self.resolve(self.spec.coded_tools))
        if self.spec.script_dir:
            os.environ["CRUCIBLE_SCRIPT_DIR"] = str(self.resolve(self.spec.script_dir))
        for key, value in self.spec.env.items():
            os.environ[key] = value


def _read_yaml(path: Path) -> object:
    if not path.is_file():
        raise ConfigError(f"file not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
