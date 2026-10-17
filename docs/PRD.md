# CRUCIBLE — Product Requirements Document

| Field | Value |
|---|---|
| Product | Crucible: chaos, fuzz and regression QA for multi-agent networks |
| Owner | Shubham Dubey |
| Status | **v1.0 — Approved for build** (changes go through a PRD changelog entry at the bottom) |
| Framework | Neuro-SAN (Cognizant AI Lab), Apache-2.0 |
| Origin | Cognizant AI Lab × IIIT Raichur Agentic AI Hackathon; built as a production product, not a demo |

---

## 1. Summary

Teams increasingly ship **multi-agent networks**: a front-man agent that delegates to specialist agents, coded tools, external networks and MCP servers. These systems fail in ways that unit tests and "does the final answer look right" evals do not catch:

- an agent **routes to the wrong specialist** because two agent descriptions overlap;
- two agents **ping-pong** a task between each other until the step budget runs out;
- a tool **times out or returns garbage** and the network confidently hallucinates around it;
- text returned by a tool **contains instructions** that hijack the network (indirect prompt injection);
- private data meant to stay in Neuro-SAN's **sly_data** channel **leaks into the LLM prompt**, where it is sent to a third-party model provider and may be echoed to the user;
- a prompt tweak in one agent silently **regresses** cost, latency or routing elsewhere.

**Crucible** is an agent network that tests agent networks. Pointed at a Neuro-SAN network, it:

1. **Lints the topology** (static graph analysis of the HOCON).
2. **Plans scenarios** that cover every delegation edge and tool edge, including adversarial personas.
3. **Injects chaos** into coded tools (latency, exceptions, malformed output, injected instructions, sly_data mutation).
4. **Runs** the scenarios and captures a **full trace**: every delegation, tool call, tool result, token count and the **exact prompt text sent to each LLM call**.
5. **Judges** the traces: loops, wrong routing, tool misuse, unhandled failures, **canary-based sly_data leak detection**, budget breaches.
6. **Diffs** against a stored baseline to catch regressions.
7. **Proposes fixes** (HOCON instruction/graph patches) and **verifies** each fix by re-running the failing scenarios and the regression set before suggesting it.

It ships as a CLI, a GitHub Action, a REST/SSE API service, a web dashboard and an MCP tool.

## 2. Problem & evidence

| Evidence | Implication |
|---|---|
| Existing tools are fragments: `looptrip` detects loops from traces only; a May-2026 paper (arXiv 2605.26521) proposes structural coverage criteria for agent workflows but ships no tool; most guidance is blog posts. | No end-to-end QA product for multi-agent networks. |
| Neuro-SAN's own `neuro_san.test` (data-driven test HOCONs, gist LLM-judge, Assessor) asserts only on **final text, returned sly_data and structure**. | Delegation behaviour, tool-failure handling and sly_data leakage are untested today. |
| Neuro-SAN explicitly markets sly_data as "private data kept out of LLM chat streams", yet nothing verifies that a given network honours it. | A leak is invisible until data reaches a model provider. |
| Agent behaviour is stochastic; a single passing run proves little. | QA must be statistical (N runs, pass ratio) and trace-aware. |

## 3. Goals and non-goals

### Goals (v1)
- G1. Find real defects in Neuro-SAN networks **before merge**, with evidence a developer can act on in minutes.
- G2. Make sly_data privacy **verifiable** (canary-based, deterministic detection).
- G3. Make agent-network changes **regression-safe** (baseline + diff in CI).
- G4. Shorten fix time with **verified** fix proposals (never an unverified suggestion labelled as a fix).
- G5. Be production-grade: deterministic where possible, reproducible runs, secure handling of secrets, observable, extensible via plugins.

### Non-goals (v1)
- Not a general LLM-app eval suite (single-prompt evals are served by promptfoo/DeepEval-class tools).
- Not runtime production monitoring/guardrails (Crucible runs pre-merge and on demand).
- Frameworks other than Neuro-SAN are **out of v1 scope**; the adapter boundary is designed so an OpenTelemetry-trace adapter can add them later.
- No automatic merge of fixes; a human always approves.

## 4. Personas

| Persona | Need | Primary surface |
|---|---|---|
| **Agent developer** (builds HOCON networks + coded tools) | "Did my change break routing / leak data / blow the budget?" | CLI, PR comment |
| **Tech lead / reviewer** | "Is this network safe to merge? Show me evidence." | PR comment, dashboard |
| **Platform / ML-ops engineer** | Gate merges, track quality/cost over time, run at scale | GitHub Action, API, dashboard |
| **Security / privacy reviewer** | Proof that private data never reaches an LLM | Leak report, SARIF |
| **Other agents / tools** | Call "audit this network" programmatically | MCP tool, REST API |

## 5. User stories (abridged; IDs referenced by FRs)

- US-1 As a developer, I run `crucible lint path/to/network.hocon` and get topology problems with file/agent locations in < 5 s.
- US-2 As a developer, I run `crucible audit <network>` and get a report of behavioural defects with trace evidence.
- US-3 As a developer, I plant canaries in sly_data and Crucible proves whether any canary reached an LLM prompt, an LLM output, the final answer, or an upstream message.
- US-4 As a developer, I see how the network behaves when a specific tool times out, errors or returns malformed/injected content.
- US-5 As a reviewer, every PR touching agent files gets a Crucible comment with pass/fail, new findings vs. baseline, and verified fix suggestions.
- US-6 As a platform engineer, I set budgets (max steps, tokens, latency, cost) and the CI gate fails when exceeded.
- US-7 As a developer, I accept a verified fix proposal and get a patch I can apply.
- US-8 As an agent, I call Crucible over MCP with a network name and receive a structured audit result.
- US-9 As a platform engineer, I browse runs, findings, delegation graphs and diffs in a dashboard.
- US-10 As a developer, I can run everything offline/deterministically (scripted mock LLM or recorded cassettes) in CI with no API keys.

## 6. Functional requirements

Priority: **P0** = core (must ship), **P1** = ship in v1 if time allows, **P2** = later.

### 6.1 Topology analysis (FR-T)
| ID | Requirement | Pri |
|---|---|---|
| FR-T1 | Load a network from a `.hocon` path or a manifest name using Neuro-SAN's own restorer (includes, commondefs resolved). | P0 |
| FR-T2 | Build a typed graph: agents (LLM agent / coded tool / toolbox / external / MCP), delegation edges, front man. | P0 |
| FR-T3 | Run Neuro-SAN's built-in validators and report their errors as findings. | P0 |
| FR-T4 | Crucible lint rules (pluggable): cycles; unreachable agents; excessive depth/fan-out; **overlapping routing descriptions** among sibling agents; missing/weak `function.description`; unbounded `max_steps`/`max_execution_seconds`; coded tools missing parameter schemas; sly_data allow-lists that pass data downstream/upstream without explicit intent; front-man misconfiguration. | P0 |
| FR-T5 | Each finding: rule id, severity, agent, message, remediation hint, source location when known. | P0 |
| FR-T6 | Output formats: human table, JSON, SARIF 2.1.0. | P0 |

### 6.2 Scenario generation (FR-S)
| ID | Requirement | Pri |
|---|---|---|
| FR-S1 | Coverage planner: enumerate delegation edges and tool edges; target ≥ 1 scenario per edge reachable from the front man. | P0 |
| FR-S2 | LLM scenario designer (Crucible agent) produces user messages + expected-route hints per target edge, plus adversarial personas (ambiguous, off-topic, injection attempts). | P0 |
| FR-S3 | Scenarios are serialised in **Neuro-SAN test-case HOCON format** (compatible with `DataDrivenTestsDriver`) with Crucible extensions under a `crucible` key. | P0 |
| FR-S4 | Hand-written scenarios are first-class and mix freely with generated ones. | P0 |
| FR-S5 | Multi-turn scenarios (`continue_conversation`). | P1 |

### 6.3 Execution & tracing (FR-E)
| ID | Requirement | Pri |
|---|---|---|
| FR-E1 | `TargetAdapter` port with **Direct** (in-process) and **HTTP** (running server) implementations. | P0 (Direct), P1 (HTTP) |
| FR-E2 | Capture MAXIMAL message stream and normalise into a `Trace` of typed spans (delegation, tool call, tool result, tool error, LLM output, final answer) with origin paths and timestamps. | P0 |
| FR-E3 | Capture **exact LLM inputs** (system + messages + tool schemas) for every model call (Direct mode) via a LangChain callback hook. | P0 |
| FR-E4 | Token/cost/latency accounting per run and per agent. | P0 |
| FR-E5 | N repetitions per scenario with configurable concurrency and per-run timeout; pass ratio semantics like Neuro-SAN `success_ratio`. | P0 |
| FR-E6 | Deterministic modes: **scripted mock LLM** (rules → tool calls/text) and **record/playback** cassettes. | P0 (scripted), P1 (cassettes) |

### 6.4 Chaos (FR-C)
| ID | Requirement | Pri |
|---|---|---|
| FR-C1 | Fault catalog: latency, exception, timeout, empty output, malformed output, oversized output, **injected-instruction output**, sly_data key removal/mutation. | P0 |
| FR-C2 | Faults target coded tools by agent name / glob, with probability and seed (reproducible). | P0 |
| FR-C3 | Injection via Neuro-SAN's supported `AGENT_ACTIVATION_PREPPER_CLASSES` hook — no edits to the target HOCON. | P0 |
| FR-C4 | Chaos matrix: run the same scenario set under each fault profile and compare. | P1 |

### 6.5 Judges (FR-J)
| ID | Requirement | Pri |
|---|---|---|
| FR-J1 | Loop / ping-pong judge (repeated A→B→A delegation patterns, repeated identical tool calls). | P0 |
| FR-J2 | Routing judge: expected route hints vs. actual delegation path; unreachable-in-practice edges. | P0 |
| FR-J3 | Tool judge: unhandled tool errors surfaced as confident answers; invalid args vs. declared schema. | P0 |
| FR-J4 | **Leak judge**: canary values planted in request sly_data; scan LLM inputs, LLM outputs, inter-agent messages, final answer and returned sly_data; report every exposure point with the span that caused it. | P0 |
| FR-J5 | Budget judge: steps, tokens, cost, latency thresholds. | P0 |
| FR-J6 | Injection judge: when an injected-instruction fault fires, detect whether the network followed it (marker-based). | P0 |
| FR-J7 | LLM semantic judge (answer quality / task success) delegating to Neuro-SAN's gist evaluator or a Crucible judge agent; always marked as probabilistic. | P1 |
| FR-J8 | Every finding carries **evidence pointers** (run id, scenario id, span ids) — no evidence, no finding. | P0 |

### 6.6 Regression (FR-R)
| ID | Requirement | Pri |
|---|---|---|
| FR-R1 | Persist runs, traces and findings (SQLite default, Postgres for service). | P0 |
| FR-R2 | Mark a run as baseline per network + branch. | P0 |
| FR-R3 | Diff: new / fixed / persisting findings; pass-ratio deltas; cost/latency deltas with tolerance. | P0 |

### 6.7 Fixes (FR-F)
| ID | Requirement | Pri |
|---|---|---|
| FR-F1 | Fix proposer (Crucible agent) produces structured patches against the HOCON (instructions, descriptions, allow-lists, limits, edges). | P0 |
| FR-F2 | Verifier applies the patch to a temporary copy, re-runs failing scenarios **and** the regression set; accepts only if the target finding disappears and no new finding appears. | P0 |
| FR-F3 | Output accepted fixes as unified diffs; rejected attempts are reported with reasons. | P0 |

### 6.8 Crucible agent network (FR-A)
| ID | Requirement | Pri |
|---|---|---|
| FR-A1 | Crucible's orchestration is itself a Neuro-SAN network: `conductor` (front man) + topology_analyst, scenario_designer, chaos_engineer, test_runner, trace_judge, leak_auditor, regression_analyst, fix_proposer, fix_verifier, report_writer. | P0 |
| FR-A2 | Deterministic work is done by coded tools wrapping the core library; LLM agents do planning/judgement and must cite evidence. | P0 |
| FR-A3 | Critic loop: fix_verifier and a report critic can reject and send work back with reasons (bounded iterations). | P0 |
| FR-A4 | Exposed as an MCP tool via the manifest. | P1 |

### 6.9 Interfaces (FR-I)
| ID | Requirement | Pri |
|---|---|---|
| FR-I1 | CLI: `lint`, `plan`, `run`, `audit`, `diff`, `fix`, `report`, `baseline`. Exit codes suitable for CI. | P0 |
| FR-I2 | Reports: Markdown, JSON, SARIF, JUnit XML. | P0 |
| FR-I3 | GitHub Action: runs audit on PRs touching agent files, posts/updates one PR comment, uploads SARIF. | P0 |
| FR-I4 | REST API + SSE progress; API-key auth; job queue. | P1 |
| FR-I5 | Web dashboard: runs list, run detail with delegation-graph view, findings with evidence, chaos matrix, diffs, fixes. | P1 |

## 7. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 Reproducibility | Every run records seed, Crucible version, Neuro-SAN version, model ids, config hash, target file hashes. Deterministic modes produce identical results across machines. |
| NFR-2 Security | API keys only from env/secret store, never logged or persisted; canary values are synthetic; Crucible never sends the target's real sly_data to its own LLM agents (uses redacted descriptors). Untrusted target coded tools run in a subprocess/container sandbox in service mode (P1). |
| NFR-3 Performance | `lint` < 5 s for 50-agent networks; audit concurrency configurable; scripted-mode audit of the bug zoo < 2 min in CI. |
| NFR-4 Cost control | Hard caps on LLM spend per audit (tokens/cost), cheap model for judges, caching of scenario generation per config hash. |
| NFR-5 Reliability | Per-run timeouts and cancellation; partial results persisted; a crashed run never corrupts the store. |
| NFR-6 Observability | Structured JSON logs (structlog), OTel traces for Crucible's own pipeline, run-level metrics. |
| NFR-7 Extensibility | Lint rules, faults, judges, reporters, adapters and stores are plugins registered via entry points / registries. |
| NFR-8 Quality | Typed (mypy strict on `src/`), ruff-clean, ≥ 85 % unit coverage on core packages; integration tests run keyless. |
| NFR-9 Portability | Python 3.13, uv; Docker images for API/worker/web; runs on Linux/macOS. |
| NFR-10 Privacy & data rules | Only synthetic or public data in examples/benchmarks (hackathon rule + good practice). |

## 8. Success metrics

| Metric | Target (v1) |
|---|---|
| Seeded-bug recall on Crucible's bug zoo benchmark | ≥ 90 % (deterministic mode: 100 %) |
| False-positive rate on clean reference networks | ≤ 5 % of findings |
| Leak judge precision/recall on planted canaries | 100 % / 100 % (deterministic) |
| Verified fixes for seeded bugs | ≥ 1 fix accepted per bug class where a config-level fix exists |
| Time from PR open to Crucible comment (scripted mode) | < 3 min |

## 9. Scope & release plan

| Release | Contents |
|---|---|
| **Core (M0–M10)** | Topology lint, bug zoo, execution + tracing, judges incl. leak, chaos, scenarios, Crucible agent network, regression store/diff, verified fix loop, reports + GitHub Action. |
| **Clients (M11–M13)** | API + worker, Next.js dashboard, MCP exposure, Docker deploy, hardening. |
| **Hackathon pack (M14)** | Architecture write-up, 1–2 page summary, demo script & video. |
| Later | OTel adapter for other frameworks, hosted service, multi-tenant orgs, scheduled audits. |

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| LLM non-determinism makes findings flaky | Statistical runs (N, ratio), deterministic scripted/cassette modes for CI, evidence-required findings. |
| Neuro-SAN internal APIs change between versions | Pin exact version; isolate all Neuro-SAN imports behind `crucible.integrations.neurosan`; contract tests on upgrade. |
| Prompt capture depends on LangChain callbacks | Primary: configure hook; fallback: OpenInference OTel; degrade gracefully (leak judge still scans stream + outputs). |
| Fix proposals that "pass" by weakening the network | Verifier also runs the regression set + clean-path scenarios; human approval required. |
| Running untrusted target code | Sandbox in service mode; CLI runs only what the developer already runs locally. |
| LLM cost of audits | Budgets, cheap judge model, caching, scripted mode by default in CI. |

## 11. Dependencies & assumptions
- Neuro-SAN pinned (currently `0.7.12`), Python 3.13.
- LLM providers: Anthropic (agents) and Google Gemini (cheap judges); keys provided via env.
- GitHub for Action/PR integration.

## 12. Glossary
- **Front man** — first agent in a Neuro-SAN network; talks to the client.
- **sly_data** — Neuro-SAN's private side channel for data that must not enter LLM context.
- **Canary** — a unique synthetic marker value planted in sly_data to detect leaks.
- **Bug zoo** — Crucible's benchmark of networks with intentionally seeded defects and their expected findings.
- **Scripted LLM** — a deterministic fake chat model that emits pre-programmed tool calls/text, used for keyless testing.

## Changelog
- v1.0 (2026-10-17): initial approved PRD.
