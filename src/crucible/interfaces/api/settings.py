"""API configuration from the environment."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from crucible.domain.errors import ConfigError


class ApiSettings(BaseSettings):
    """``CRUCIBLE_PROJECTS="zoo=examples/targets;shop=/srv/agents"``, ``CRUCIBLE_API_KEYS="k1,k2"``."""

    model_config = SettingsConfigDict(env_prefix="CRUCIBLE_", env_file=".env", extra="ignore")

    home: Path = Path(".crucible")
    projects: str = ""
    api_keys: str = ""
    cors_origins: str = "http://localhost:3000"

    project_map_override: dict[str, Path] | None = Field(default=None, exclude=True)

    def project_map(self) -> dict[str, Path]:
        """Registered projects by name."""
        if self.project_map_override is not None:
            return dict(self.project_map_override)
        out: dict[str, Path] = {}
        for item in filter(None, (p.strip() for p in self.projects.split(";"))):
            name, sep, path = item.partition("=")
            if not sep or not name or not path:
                raise ConfigError(f"bad CRUCIBLE_PROJECTS entry '{item}' (expected name=path)")
            out[name.strip()] = Path(path.strip()).resolve()
        return out

    def keys(self) -> list[str]:
        """Accepted API keys (empty = auth disabled, development only)."""
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]

    def origins(self) -> list[str]:
        """CORS origins."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
