# ADR 0002 — In-process execution, session reuse and timeout semantics

Date: 2026-10-17 · Status: Accepted

## Context
Crucible runs target networks in-process via Neuro-SAN's `DirectAgentSession` to capture full MAXIMAL traces and
exact LLM inputs (LangChain configure hook). Measured: creating a session ≈ 2.9 s, a chat on it ≈ 30 ms.

## Decisions
1. **Reuse one session per adapter** (reset per turn); recreate only after failures.
2. **Prompt capture is process-global and serialised** by a lock: runs execute sequentially in one process so every
   captured LLM call belongs to exactly one run. Parallelism will come from multiple worker processes (M11).
3. **Hard timeouts abandon, not close, the session.** Closing a `DirectAgentSession` shuts down executor queues shared
   with sessions created later (observed `QueueShutDown` in the next run). After a hard timeout the adapter waits
   (bounded by the network's `max_execution_seconds` + 5 s, max 120 s) for the runaway request to stop, so it cannot
   interfere with the next run. Networks without `max_execution_seconds` are flagged by lint (`topology/unbounded-budget`).
4. Status: `timeout` if the hard limit fired or Neuro-SAN reports "Agent timed out"; `error` on adapter exceptions or
   Neuro-SAN error answers; otherwise `ok`. Status says nothing about correctness — judges decide that.

## Consequences
In-process execution is fast and fully observable but not isolated; untrusted targets and true parallelism need the
subprocess worker planned for service mode.
