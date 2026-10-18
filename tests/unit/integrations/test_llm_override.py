"""LLM override: spec parsing and config rewriting."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from crucible.domain.errors import ConfigError
from crucible.integrations.neurosan.llm_override import (
    override_llm,
    parse_llm_spec,
    variant_dir,
    write_llm_variant,
)


def test_parse_provider_model_and_params() -> None:
    assert parse_llm_spec("gemini:gemini-3.5-flash-lite,max_tokens=1024,temperature=1.0") == {
        "class": "gemini",
        "model_name": "gemini-3.5-flash-lite",
        "max_tokens": 1024,
        "temperature": 1.0,
    }
    assert parse_llm_spec("claude-sonnet-5-5") == {"model_name": "claude-sonnet-5-5"}


@pytest.mark.parametrize("spec", ["", "nope:model", "gemini:", "gemini:x,badparam"])
def test_parse_rejects_bad_specs(spec: str) -> None:
    with pytest.raises(ConfigError):
        parse_llm_spec(spec)


def test_override_replaces_top_level_and_per_agent_without_mutating() -> None:
    config = {
        "llm_config": {"class": "scripted"},
        "tools": [{"name": "a", "llm_config": {"class": "scripted"}}, {"name": "b", "class": "tool.T"}],
    }
    llm = {"class": "gemini", "model_name": "m"}
    out = override_llm(config, llm)
    assert out["llm_config"] == llm
    assert out["tools"][0]["llm_config"] == llm
    assert "llm_config" not in out["tools"][1]
    assert config["llm_config"] == {"class": "scripted"}


def test_write_variant_keeps_stem_and_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "desk.hocon"
    source.write_text('{"llm_config": {"model_name": "x"}, "tools": [{"name": "desk", "instructions": "hi"}]}')
    llm = {"model_name": "y"}
    path = write_llm_variant(source, llm, tmp_path / "out")
    assert path.name == "desk.hocon"
    assert path.parent == variant_dir(tmp_path / "out", source, llm)
    assert json.loads(path.read_text())["llm_config"] == llm
    assert write_llm_variant(source, llm, tmp_path / "out") == path
