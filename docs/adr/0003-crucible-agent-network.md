# ADR 0003 — Crucible's own agent network: packaging, keyless mode, nesting

Date: 2026-10-17 · Status: Accepted

## Decisions
1. **Coded tools are referenced by fully-qualified class** (`crucible.integrations.neurosan.agent_tools.X`), so the
   network works from the installed wheel and independently of the target project's `AGENT_TOOL_PATH`.
2. **Tool logic lives in `services/toolkit.py`** (framework-free, unit-tested). Coded tools are thin adapters that read
   `project_dir`/`target` from sly_data and return compact JSON with short finding ids; evidence is pre-masked, so
   Crucible's own LLM agents never see target secrets.
3. **Keyless mode is generated at runtime**: parse `crucible.hocon`, swap `llm_config` (top-level *and* per agent —
   Neuro-SAN's filter chain copies it into each agent spec) for `ScriptedChatModel`, write to `$CRUCIBLE_HOME/agents/`.
   A static `include`-based variant failed because Neuro-SAN resolves includes against its own registry dir.
4. **The outer (Crucible) session is not prompt-captured.** Its tools run nested target sessions that take the
   process-global capture lock; capturing the outer session would deadlock. Target activation (`Project.activate`)
   happens before the outer session is created so activation factories see valid tool paths.
5. Specialists use explicit `request` parameters rather than the AAOSA Determine/Fulfill handshake: routing is
   unambiguous by design and it halves LLM calls per hand-off.

## Consequences
Agentic and deterministic audits share one pipeline (AuditService); the agent layer adds planning, scenario design
(evaluation loop through `save_scenarios` validation), root-cause explanation and reporting.
