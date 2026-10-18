# Architecture overview

## Principle: deterministic core, agentic brain
- **Facts** (graph structure, canary hits, loops, metrics, diffs, patch application) are computed by deterministic, unit-tested code.
- **Judgement** (which scenarios matter, why routing failed, how to fix it) is done by Neuro-SAN agents that call the core through coded tools.
- **Every conclusion cites evidence** (run id / scenario id / span ids). Critics reject uncited or unverified output.

## System context

```
            ┌──────────── developer / CI / other agents ────────────┐
            │  CLI        GitHub Action      REST+SSE API     MCP    │
            └─────┬────────────┬──────────────────┬───────────┬─────┘
                  │            │                  │           │
                  ▼            ▼                  ▼           ▼
        ┌───────────────────────────────────────────────────────────┐
        │                 Crucible application layer                 │
        │  AuditService: lint → plan → run(+chaos) → judge → diff →  │
        │                fix(verify) → report                        │
        │  (driven directly, or by the Crucible agent network)       │
        └──┬──────────┬──────────┬─────────┬─────────┬─────────┬────┘
           │          │          │         │         │         │
       topology   scenarios  execution   judges  regression  fixes
           │                     │  ▲
           │                     │  │ traces (MAXIMAL stream + captured LLM prompts)
           ▼                     ▼  │
     integrations/neurosan ── loader · sessions · ChaosActivationPrepper · prompt-capture callback · ScriptedChatModel
                                 │
                                 ▼
                     Target Neuro-SAN network (HOCON + coded tools)
```

## Crucible's own agent network (Neuro-SAN, AAOSA)
```
conductor (front man: plans the audit; 8 children)          src/crucible/agents/registries/crucible.hocon
├── topology_analyst   → lint_network
├── scenario_designer  → coverage_plan, save_scenarios      (evaluation loop: invalid scenarios are rejected)
├── test_runner        → run_audit                          (lint + run + judge; audit id stored in sly_data)
├── investigator       → leak_report, finding_evidence      (leak proof + root cause from masked evidence)
├── fix_lead           (critic loop, max 2 rounds)
│   ├── fix_proposer   → propose_fixes                      (deterministic proposals; LLM may refine ops)
│   └── fix_verifier   → verify_fixes                       (re-audit patched copy; accept only if fixed & nothing new)
├── regression_analyst → regression_diff                    (new vs. baseline = merge gate)
├── chaos_engineer     → chaos_matrix
└── report_writer      → render_report
Coded tools: crucible.integrations.neurosan.agent_tools (thin) -> crucible.services.toolkit (logic). ADR 0003.
```
Raw target sly_data and canaries never enter Crucible's own LLM prompts; agents see finding ids, rule ids and redacted excerpts.

## Packages (see `CONTRIBUTING.md` for layering rules)
| Package | Responsibility | Key types |
|---|---|---|
| `domain` | Models shared everywhere | `NetworkGraph`, `AgentNode`, `Edge`, `Finding`, `Evidence`, `Scenario`, `Run`, `Trace`, `Span`, `FaultSpec`, `FixProposal` |
| `integrations/neurosan` | All Neuro-SAN coupling | `load_network`, `NeuroSanDirectAdapter`, `ChaosActivationPrepper`, `PromptCaptureHandler`, `ScriptedChatModel` |
| `topology` | Graph + lint | `build_graph`, `LintRule` port, rule registry |
| `execution` | Run scenarios, normalise traces | `TargetAdapter` port, `Runner`, `TraceNormaliser` |
| `chaos` | Faults | `Fault` port, catalog, `ChaosPlan` |
| `scenarios` | Coverage + fixtures | `CoveragePlanner`, HOCON fixture I/O |
| `judges` | Trace analysis | `Judge` port, registry |
| `regression` | Baselines + diffs | `RunDiff` |
| `fixes` | Patch + verify | `HoconPatch`, `FixVerifier` |
| `reporting` | Output formats | `Reporter` port (md/json/sarif/junit) |
| `storage` | Persistence | `RunRepository`, `ArtifactStore` |
| `interfaces` | CLI / API / worker | typer app, FastAPI app |

## Data flow of one audit
1. `load_network(path)` → `NetworkGraph` (+ raw config) — via Neuro-SAN's `AgentNetworkRestorer`.
2. Lint rules → `Finding[]` (static).
3. Coverage planner → target edges → scenarios (generated + hand-written).
4. For each scenario × chaos profile × repetition: adapter runs the target with canaries planted in sly_data; collects MAXIMAL stream + captured LLM inputs → `Trace`.
5. Judges over traces → `Finding[]` with evidence.
6. Diff vs baseline → new/fixed/persisting.
7. Fix loop on selected findings → verified `FixProposal[]`.
8. Reporters → Markdown / JSON / SARIF / JUnit; persisted run.

## Live models and spend (M15, ADR 0004)
- `--target-llm` / `--agent-llm` swap any network's `llm_config` (top-level + per agent) into a parsed copy; the hook is
  `Project.network_path`, so every surface inherits it.
- Every LLM call is priced (`integrations/neurosan/pricing.py`, Neuro-SAN's price table, captured via `on_llm_end`);
  the Runner checks a `BudgetGuard` before each run and charges a cumulative ledger after it.

## Deployment (service mode, M11+)
API (FastAPI) + worker (job queue) + Postgres + artifact store (fs/S3) + web (Next.js). Target coded tools run inside the worker sandbox. Docker Compose for local/prod-like deploy.
