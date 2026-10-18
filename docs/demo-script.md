# Demo script

## Recorded video: "Test the middle" (3:00)

| # | Time | Picture | Narration |
|---|---|---|---|
| 1 | 0:00 | Cold open: the real runaway trace scrolls, the hand-off counter climbs to 71, TIMEOUT 60 s | One refund request. A real support network, running on Gemini. Billing asks payments. Payments asks billing. Seventy-one hand-offs later, it times out. A test that checks only the final answer would never know why. |
| 2 | 0:20 | Title: Crucible, an agent network that tests agent networks | This is Crucible. An agent network that tests agent networks. |
| 3 | 0:28 | Four failure cards with live stats (loops 2/13, leaks 15/15, masked errors 13/13, injection 2/2 flagged) | Multi-agent systems fail in the middle. They loop. They leak private data into prompts. They hide tool failures behind confident answers. And they obey instructions planted in web pages. |
| 4 | 0:45 | One audit: lint → scenarios → canaries → traces → chaos → findings; facts vs judgement | Crucible reads the network's configuration, generates scenarios, plants canaries in private data, records every prompt and hand-off, injects chaos into tools, and judges the traces. Facts come from deterministic code. Judgement comes from Crucible's own agents. |
| 5 | 1:06 | **Live dashboard**: support_loop graph → Run audit (13 reps, 74× speed-up) → findings: ping-pong 5/13, timeout, budget | Here is the dashboard, auditing the live network on Gemini. The graph already shows the cycle. Run the audit, and the findings arrive with proof. Billing and payments ping-ponged in five of thirteen runs, and one run blew through its time and delegation budget. |
| 6 | 1:26 | **Live**: account_leak audit → leak finding → run trace → exact LLM input with [REDACTED] | Private data is subtler. The customer's national ID never appeared in an answer. But it sat inside the prompt sent to the model, in every single run. Crucible proves the leak from the captured prompt, and masks the secret in its own report. |
| 7 | 1:49 | **Live**: Find verified fixes → ACCEPTED, 5 findings resolved, config diff | And Crucible does not just complain. It patches a copy of the network, re-runs every scenario, and accepts a fix only if the defect is gone and nothing new appears. |
| 7b | 2:03 | The fix that lied: v1 ACCEPTED → "refund approved" (real answer) → new rule dangling-reference → v1 REJECTED → v2 honest answer | Live testing kept us honest. Our first accepted fix stopped the loop, and the model began telling customers their refund was approved. So Crucible learned a new rule, and now rejects fixes like that. |
| 8 | 2:21 | Crucible's own network (conductor, 8 specialists, fix critic loop) + live MCP tools/call → NOT SAFE TO MERGE | Crucible is itself a Neuro-SAN agent network. A conductor and its specialists plan the audit, explain root causes, and run the fix critic loop. And any agent can call it over MCP. |
| 9 | 2:38 | Live benchmark tiles: 100% recall, 100% precision, 6 bugs, ₹26; surfaces | On live Gemini runs, it found every seeded defect with no false alarms, after we fixed six bugs that only real models exposed. All of this testing cost about twenty-six rupees. |
| 10 | 2:53 | Close: Test what happens in the middle. Repo, Neuro-SAN, hackathon | Crucible. Test what happens in the middle. |

Video file: [docs/assets/demo/crucible-demo.mp4](assets/demo/crucible-demo.mp4). Every number on screen comes from
[docs/eval/live.md](eval/live.md) or from the footage itself.

## Live walkthrough

The live walkthrough below is for presenting in person (about 5 minutes).

Setup (once): `uv sync`, `cd web && pnpm install && pnpm build`.
Terminal A: `CRUCIBLE_PROJECTS="zoo=examples/targets" CRUCIBLE_API_KEYS=demo uv run crucible serve --port 8765`
Terminal B: `cd web && CRUCIBLE_API_KEY=demo pnpm start` → http://localhost:3000
(Live mode: export ANTHROPIC_API_KEY and drop `--scripted`; everything else is identical.)

1. **The problem (30 s)** — show `examples/targets/registries/support_loop.hocon`: two specialists that "ask each
   other when unsure". `crucible run examples/targets -t support_loop` → 150+ hand-offs, timeout.
2. **Static lint (30 s)** — `crucible lint examples/targets/registries/*.hocon`: cycle, routing overlap, wildcard
   sly_data, unbounded budget, before running anything.
3. **Dashboard audit (60 s)** — open support_loop: graph shows the cycle in red. Click *Run audit* → live SSE progress
   → findings: ping-pong (154 hand-offs, evidence spans), timeout, budget.
4. **Verified fix (45 s)** — *Find verified fixes* → ACCEPTED: remove back-edge, "4 findings resolved, no new
   findings", coloured config diff. A cosmetic fix would be REJECTED by the verifier.
5. **Leak proof (45 s)** — account_leak audit: `leak/sly-data-exposure` first emitted by `profile_lookup`, seen in
   the LLM prompt and the answer; open the run trace → *Exact LLM inputs* show `[REDACTED]` where the secret was.
6. **Chaos + injection (45 s)** — `crucible chaos examples/targets -t clean_concierge` (resilience matrix);
   `crucible audit examples/targets -t injectable_research` → agent emailed notes to `exfil@attacker.test`.
7. **Crucible is a Neuro-SAN network (45 s)** — `crucible audit examples/targets -t fragile_weather --agentic
   --scripted`: 17 hand-offs conductor → specialists → tools → verified fix → report. Then
   `crucible mcp-server examples/targets -t fragile_weather --scripted` and call it over MCP.
8. **Merge gate + evaluation (30 s)** — `crucible bench` → recall 100% / precision 100%; show the GitHub Action
   summary (`docs/guides/github-action.md`).
