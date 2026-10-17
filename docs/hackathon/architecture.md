# Crucible — architecture (for reviewers)

```
            developer / CI / IDE agent / dashboard
   CLI · GitHub Action · REST+SSE API · MCP tool (Neuro-SAN server)
                          │
        ┌─────────────────┴──────────────────┐
        │  Crucible agent network (Neuro-SAN) │  src/crucible/agents/registries/crucible.hocon
        │  conductor → topology_analyst, scenario_designer, test_runner, investigator,
        │              fix_lead → {fix_proposer ⇄ fix_verifier}, regression_analyst,
        │              chaos_engineer, report_writer        (11 LLM agents, 11 coded tools)
        └─────────────────┬──────────────────┘
                          │ coded tools (ids + masked JSON only)
        ┌─────────────────┴──────────────────────────────────────────────────┐
        │ deterministic core (src/crucible)                                   │
        │ topology lint · scenarios/coverage · execution+tracing · chaos ·    │
        │ judges · regression · verified fixes · reporting · storage          │
        └─────────────────┬──────────────────────────────────────────────────┘
                          │ integrations/neurosan (the only Neuro-SAN coupling)
     loader (AgentNetworkRestorer) · DirectAgentSession runs (MAXIMAL stream) ·
     LangChain prompt-capture hook · ActivationPrepper chaos · ScriptedChatModel
                          │
                 target Neuro-SAN network (HOCON + coded tools)
```

## How Neuro-SAN is used
| Neuro-SAN feature | How Crucible uses it |
|---|---|
| HOCON agent networks, AAOSA-style delegation | Crucible's own 11-agent network; targets are loaded with `AgentNetworkRestorer` |
| Coded tools | 11 Crucible tools (fully-qualified classes); target tools are wrapped for chaos |
| `sly_data` | Project/target context and audit ids flow through sly_data; target secrets are tracked, canaried and proven never to leave it |
| `ActivationPrepper` extension point | Fault injection into target coded tools without editing the network |
| MAXIMAL chat stream + journals | Delegation/tool/error/tokens trace normalised into spans |
| Validators | Bridged into lint findings (deduplicated) |
| `neuro_san.test` data-driven tests | Scenarios export to Neuro-SAN test-case HOCON, verified with `DataDrivenAgentTestDriver` |
| Server MCP support | `crucible mcp-server` serves Crucible as an MCP tool |
| LLM config (`anthropic`, `gemini`, custom class) | Live agents on Claude/Gemini; `ScriptedChatModel` for keyless deterministic CI |

## Key decisions (ADRs in docs/adr)
- 0001: deterministic core + agentic brain; all Neuro-SAN coupling in one package; extend Neuro-SAN's test stack.
- 0002: in-process execution with session reuse (create ≈ 3 s, chat ≈ 30 ms); prompt capture serialised; hard
  timeouts abandon + drain rather than close a session (closing broke the next session).
- 0003: Crucible's network packaging, runtime-generated keyless variant, no prompt capture on the outer session.

## Evaluation loops
1. scenario_designer → save_scenarios validation (invalid scenarios are rejected with reasons) → re-audit.
2. fix_lead: fix_proposer → fix_verifier re-audits a patched copy → rejection reasons go back (max 2 rounds).
3. The bug-zoo benchmark scores Crucible itself (recall/precision) on every CI run.
