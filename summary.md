# Crucible — project summary
**An agent network that tests agent networks.** Cognizant AI Lab × IIIT Raichur Agentic AI Hackathon · Built on Neuro-SAN
Author: Shubham Dubey (IIIT Raichur)

## The problem
Multi-agent systems are being shipped with almost no quality assurance. Their worst failures are invisible to the
"is the final answer right?" evals teams use today:
- specialists **ping-pong** a task until the time budget dies (we measured 387 hand-offs in 30 s on a two-agent loop
  that had `max_steps: 40` — Neuro-SAN's step limit does not bound nested delegation);
- a tool **fails** and the network answers confidently anyway;
- a fetched web page **injects instructions** and the agent emails user data to an attacker;
- private data meant for Neuro-SAN's `sly_data` channel **leaks into LLM prompts** and the user-facing answer.
Existing tools are fragments (loop detectors over traces, a 2026 paper on coverage criteria without code) and
Neuro-SAN's own test framework checks only final text and returned data.

## The solution
Crucible points at a Neuro-SAN network and runs a full QA pipeline — **itself implemented as a Neuro-SAN network**:
1. **Topology lint** (12 rules + Neuro-SAN's validators): cycles, unreachable agents, overlapping routing
   descriptions, unbounded budgets, wildcard sly_data allow-lists.
2. **Coverage-driven scenarios**: measures which delegation edges are exercised; designs scenarios for the gaps
   plus adversarial probes; exports Neuro-SAN-native test cases.
3. **Execution with full traces**: every hand-off, tool call, tool error, token, and the **exact prompt of every LLM
   call** (LangChain hook), with canaries planted in sly_data.
4. **Chaos engineering** (9 fault kinds) through Neuro-SAN's supported activation-prepper extension point — no edits
   to the network under test.
5. **9 judges** with evidence pointers: ping-pong, timeouts, budgets, *proven* sly_data leaks (exact-value match,
   first-emitter attribution, masked evidence), masked tool errors, indirect prompt injection, routing, answers.
6. **Regression gate**: baselines + diffs so CI fails only on *new* defects.
7. **Verified fixes**: proposals are applied to a copy of the network and re-audited; a fix is accepted only if its
   finding disappears and nothing new breaks (critic loop).

## Multi-agent design (Neuro-SAN)
A conductor plans the audit and coordinates 10 specialists — topology analyst, scenario designer, test runner,
investigator, fix lead (→ fix proposer ⇄ fix verifier critic loop), regression analyst, chaos engineer, report
writer — backed by 11 coded tools. Deterministic facts come from tested code; agents plan, explain root causes and
propose fixes, and must cite tool ids. Private data never reaches Crucible's own agents (sly_data carries the
project context; evidence is masked). Crucible linted its own network and caught a fan-out smell in its first design,
which led to the hierarchical fix-lead/investigator structure.

## Evaluation loop and results
- **Bug-zoo benchmark** (5 networks with seeded defects + ground truth, runs keyless): **recall 100%, precision 100%**,
  enforced in CI.
- **Verified fix loop on the zoo**: ping-pong fixed by removing a back-edge (4 findings resolved, nothing new);
  masked error and prompt injection fixed by instruction patches; the leak correctly flagged as a code change.
- **Live validation on Gemini** (realistic target networks, 3 repetitions per scenario): recall **100%**, precision
  **100%** on fresh runs. Real models looped (2 of 13 runs ran until the 60 s limit), leaked a national id into the
  prompt in 15 of 15 runs, and invented forecasts after a tool outage in 13 of 13. Live testing also exposed six
  Crucible defects, all fixed and covered by tests. Full results and limits: `docs/eval/live.md`.
- Crucible's own agents ran live on Gemini with correct NOT-SAFE verdicts, and every cited id was checked against the
  stored audits. All live testing cost about ₹26.
- 174 automated tests (unit, Neuro-SAN integration, API, MCP end-to-end); the dashboard was verified with Playwright.

## Delivered surfaces
CLI (`lint, run, audit, chaos, plan, fix, diff, bench, serve, mcp-server …`), GitHub Action (SARIF, sticky PR
comment, gate on new findings), REST + SSE API with API keys, Next.js dashboard, and an **MCP tool served by
Neuro-SAN's own server**. Data used: synthetic only. Demo video: `docs/assets/demo/crucible-demo.mp4` (3 min).

## Impact
Every team building agent networks needs a merge gate for agent behaviour, not just answers. Crucible turns
"we hope the agents behave" into evidence: which hand-off looped, which tool's output leaked which sly_data key into
which prompt, and a verified patch to fix it.
