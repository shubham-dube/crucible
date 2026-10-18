# ADR 0004: Live-LLM validation (model override, per-call spend, adjudicated ground truth)

- Status: accepted
- Date: 2026-10-18

## Context
Crucible was built and benchmarked against `ScriptedChatModel` targets, which are deterministic and keyless. Real
models behave differently:
- they loop only sometimes;
- they resist some injections;
- they hedge ("the service is down, but expect ~36 °C").

Live runs also cost money. Neuro-SAN reports token accounting only when a run finishes, so the expensive runs (the
runaway loops) were the ones the ledger under-counted.

## Decision
1. **Override, don't fork.** `--target-llm` / `--agent-llm` (`CRUCIBLE_TARGET_LLM` / `CRUCIBLE_AGENT_LLM`) rewrite the
   top-level and per-agent `llm_config` into a parsed copy under `$CRUCIBLE_HOME/llm_variants/`. They hook in through
   `Project.network_path`, so every surface (CLI, API, toolkit, fixes) gets the override in one place.
2. **Price every call.**
   - Prompt capture also records LangChain `on_llm_end` usage per call and prices it with Neuro-SAN's own model table
     (`integrations/neurosan/pricing.py`).
   - A run uses the larger of the reported and captured totals.
   - Spend goes to a cumulative JSONL ledger. `CRUCIBLE_LLM_BUDGET_USD` / `_CALLS` refuse to start new runs once
     reached.
3. **Separate live targets with adjudicated ground truth.**
   - `examples/live_targets/` keeps the zoo's design flaws in natural language.
   - Expected findings come from reading traces.
   - Model-dependent behaviour goes into `allowed:`, so it is neither required nor counted as a false positive.
4. **Repetitions by default for live work.** `bench`, `fix` and the agentic test_runner use `-n 3`. Fix verification
   re-runs with the audit's repetition count.

## Consequences
- Live numbers are honest about variance, but the ground truth involves human judgement; `docs/eval/live.md` lists the
  caveats.
- Agent sessions served by Neuro-SAN's own server (MCP) are outside the ledger.
- Judges stay deterministic. Gaps that only an LLM judge could close (fabricated non-numeric facts) are documented
  rather than hidden.
