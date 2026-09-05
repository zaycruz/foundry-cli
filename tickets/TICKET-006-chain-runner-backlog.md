# TICKET-006: Stateful chain runner + workflow composition layer (backlog)

**Status**: Backlog — deferred until composite mutation tools ship (see active goal)
**Priority**: Low — no trace evidence for the core hypothesis yet
**Found**: 2026-07-27 brainstorm (workflow tools that chain calls)

## Summary

Original brainstorm framing: workflow tools that chain CLI calls into
composable multi-step operations, e.g. `tag → watch build → verify function
release`. Deferred in favor of composite mutation tools + self-correcting
errors after Langfuse evidence showed where the actual pain lives.

## Evidence snapshot (Langfuse `foundry-agent-session`, 38 sessions / 636 calls)

- **Zero polling/waiting loops observed.** No build-status or transaction
  polling anywhere in the sample. The stateful-chaining hypothesis
  (watch-and-continue) currently has no supporting evidence.
- The repeated real-world "chain" is preflight→mutate→verify, which the
  active goal absorbs into single composite commands instead.
- Discovery overhead (54% `tool_search`) and the 32% retry tax are addressed
  by the active goal, not by chaining.

Caveat: sample is benchmark-harness runs, not organic usage. Organic
release workflows (tag → publish build → version check) may still justify
stateful chains.

## Scope if picked up

1. **Composite-op primitives first** — the goal's composite tools become the
   chainable steps (each already plan-first, idempotent-ish, self-verifying).
2. **Chain runner** — execute an ordered sequence of composite ops with
   stop-on-failure and per-step artifacts. Candidate shapes: declarative
   YAML/JSON pipeline (`foundry run pipeline.yaml`), or agent-manifest-level
   composite tool registration.
3. **Stateful waiting** — only if organic evidence appears: poll-with-timeout
   step type (e.g. wait for build RID to reach terminal state, wait for
   function version to become queryable). Release-watch (tag → build →
   `functions query execute --version`) is the reference use case.
4. **Notifications** — diff-based watcher over `repository context` tag lists
   / `orchestration builds search` / function versions, with a state file.
   No webhook surface exists in Foundry or the MCP; polling is the honest
   mechanism.

## Revisit triggers

- Composite mutation tools shipped and adopted (active goal complete).
- Trace evidence of agents manually polling builds/transactions.
- The repository tag/release work (push-permission probe → `repository tag`
  command group) lands, creating a concrete chain to automate.

## Related

- `tickets/TICKET-001..005` — proposal/preview leads (separate track).
- Repo tag/release discussion: `RepositoryService.list_tags` exists
  internally; git smart-HTTP push permission is the gating unknown.
