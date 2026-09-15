# Architecture

OpenRD is a **plugin micro-kernel** plus a long-horizon R&D loop.

## Kernel

`Context` holds named services (`llm`, `archive`, `sandbox`, …), typed events, and reversible `apply()` registrations. A **profile** (`src/openrd/profiles/*.yaml`) is an ordered bundle list. Plugins declare `plugin.yaml` so the LLM receives a catalog of tools and *when to use them*.

## Memory

- **Journal** — append-only events (source of truth, resume/replay).
- **Core blocks** — tiny always-on RAM (goal, champion, bans, budget).
- **Archive** — BM25 + embeddings; canonical URL/query keys block repeats.
- **Graph** — Goal–Line–Hypothesis–Run–Paper–Claim.
- **Compiler** — AIDE-style Σ(T) brief with hard token budgets. The model is forbidden from stuffing the full INDEX into context.

## Orchestration

One orchestrator owns the DAG:

Understand → Research → Ideate → Critique → Select → Implement → Screen → FullEval → Analyze → UpdateMemory.

Think-pool (N−1) vs exec-pool (hardware-gated, default 1). Blackboard locks on `mechanism` and `url`. Parallel agents get different slices; they share summaries, not raw chats.

Critique encodes the old protocol: quality bar, cemetery-by-class, novelty cosine, debate veto, refine quotas, noise-floor promote gate.

## Safety

Hypothesis text + AST/regex on code. Sandbox: Docker (`network=none`, memory, pids, no-new-privs) or local rlimits. Secrets stripped from the subprocess env.

## UI

React control plane: providers (Polza OpenAI-compat), projects, live tree, metrics, ₽ ledger, steer/rollback/PDF drop, plugin list.
