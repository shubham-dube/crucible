# ADR 0001 — Record architecture decisions; foundational choices

Date: 2026-10-17 · Status: Accepted

## Context
Crucible is built incrementally, module by module. Every non-obvious decision is recorded in the repository so that
contributors and reviewers can follow why the system looks the way it does.

## Decisions
1. **ADRs** in `docs/adr/NNNN-title.md` for every non-obvious decision.
2. **Target framework: Neuro-SAN first**, pinned exactly (0.7.12). All coupling isolated in `crucible.integrations.neurosan`.
3. **Python 3.13 + uv**, single package `crucible-agents` (import name `crucible`), src layout. A monorepo with multiple Python packages was rejected as premature.
4. **Deterministic core + agentic brain**: facts in code, judgement in agents, evidence required.
5. **Extend Neuro-SAN's test stack** (test-case HOCON format, evaluators) instead of inventing a parallel format.
6. **Chaos via `AGENT_ACTIVATION_PREPPER_CLASSES`** (supported hook, no target edits) rather than monkeypatching.
7. **Own `ScriptedChatModel`** for deterministic keyless tests (Neuro-SAN's `ChatMockLlm` only echoes and needs tiktoken downloads).
8. **Storage**: SQLite by default (zero-config CLI), Postgres in service mode, behind a repository port.
9. **Frontend**: Next.js + TypeScript + Tailwind + shadcn/ui.
10. **License**: Apache-2.0 (same as Neuro-SAN).

## Consequences
Upgrading Neuro-SAN means re-verifying `docs/architecture/neurosan-integration.md` and the integration contract tests.
