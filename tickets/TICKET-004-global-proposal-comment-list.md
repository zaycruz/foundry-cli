# TICKET-004: Investigate global-proposal `comment` and `list`

**Status**: Needs UI capture — leads only
**Priority**: Low — quality-of-life actions, not lifecycle blockers
**Found**: 2026-07-27 parity swarm (agent-16)

## Summary

Two fail-closed global-proposal actions with weaker leads. Both likely
depend on endpoints absent from every published client, so live UI capture
is the only path to a contract.

## Lead 1: `comment` via the generic comments service

- The sourcemap contains a generic `CommentService` (`@palantir/comments-api`,
  service name `comments`) with `addComment(resourceId, …)`. The MCP uses it
  for pull-request RIDs. Whether a branch or proposal RID is a valid
  `resourceId` is unverified.
- The Global Branching docs describe a comments section on branch pages
  (https://www.palantir.com/docs/foundry/global-branching/application/).
- **Capture**: post a comment on a branch/proposal in the UI; record service
  base path, `resourceId` format, and body. Then probe with a disposable
  proposal RID.

## Lead 2: `list` via the Global Branching app

- Evidence of absence in published clients: no list/search method in
  `BranchService`, `OntologyBranchService`, the SDK, or Palantir's MCP.
  The CLI's module docstring already records "load-by-RID only"
  (`global_branching.py:5-6`).
- But the Global Branching app's Proposals tab does list proposals, so a
  frontend endpoint exists somewhere.
- **Capture**: open the Proposals tab with devtools; record the listing
  request (service, path, pagination, filters).

## Work items (only after a captured contract)

1. Add the captured route to `GlobalProposalService` (or a comments service
   wrapper) behind the standard evidence comments.
2. Wire `pltr proposal comment global-proposal` and/or
   `pltr proposal list global-proposal`; update
   `SDK_REACHABLE_CAPABILITIES` and reasons map.
3. Tests, docs (`reference/proposal-commands.md`,
   `reference/global-branching-commands.md`), CHANGELOG.

## Acceptance criteria

- Captured request/response contract recorded in the ticket and service
  docstring, or the lead recorded as killed with the capture evidence.
- If implemented: command works end-to-end on a live deployment, tests green.

## Out of scope

- Comment threading/reactions; list filtering beyond what the captured
  endpoint natively supports.
