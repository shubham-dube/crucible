"""Price LLM usage with Neuro-SAN's own model table, so Crucible's numbers match Neuro-SAN's token accounting."""

from __future__ import annotations

from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def _pricer() -> Any:
    from neuro_san.internals.run_context.langchain.llms.llm_info_restorer import LlmInfoRestorer
    from neuro_san.internals.run_context.langchain.token_counting.llm_token_callback_handler import (
        LlmTokenCallbackHandler,
    )

    return LlmTokenCallbackHandler(LlmInfoRestorer().restore())


def usage_of(response: Any) -> tuple[int, int, str]:
    """``(prompt_tokens, completion_tokens, model_name)`` of a LangChain ``LLMResult`` (zeros when unreported)."""
    from neuro_san.internals.run_context.langchain.token_counting.llm_token_callback_handler import (
        LlmTokenCallbackHandler,
    )

    usage, model, _ = LlmTokenCallbackHandler._extract_usage(response)
    if not usage:
        return 0, 0, str(model or "")
    return int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0), str(model or "")


def cost_usd(model: str | None, prompt_tokens: int, completion_tokens: int) -> float:
    """USD cost; 0.0 for models without a price (e.g. ScriptedChatModel)."""
    if not model or not (prompt_tokens or completion_tokens):
        return 0.0
    name = model.removeprefix("models/")
    return float(_pricer().calculate_token_costs(name, completion_tokens, prompt_tokens) or 0.0)
