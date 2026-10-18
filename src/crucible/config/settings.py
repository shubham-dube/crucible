"""Process-wide settings from the environment (``CRUCIBLE_`` prefix) and ``.env``."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Crucible settings. Provider keys use their conventional names, everything else ``CRUCIBLE_*``."""

    model_config = SettingsConfigDict(env_prefix="CRUCIBLE_", env_file=".env", extra="ignore")

    home: Path = Field(default=Path(".crucible"), description="where runs, baselines and artifacts are stored")
    log_level: str = "INFO"
    log_json: bool = False
    agent_model: str = "claude-sonnet-5-5"
    judge_model: str = "gemini-3-flash"
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    google_api_key: SecretStr | None = Field(default=None, alias="GOOGLE_API_KEY")
    target_llm: str | None = Field(default=None, description="run targets on this LLM, e.g. gemini:gemini-3.5-flash")
    agent_llm: str | None = Field(default=None, description="run Crucible's own agents on this LLM")
    llm_budget_usd: float | None = Field(default=None, description="stop when the spend ledger reaches this")
    llm_budget_calls: int | None = Field(default=None, description="stop when the ledger reaches this many calls")
    usd_inr: float = Field(default=88.0, description="exchange rate used only for displaying spend")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
