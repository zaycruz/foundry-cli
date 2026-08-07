# TICKET-003: Implement global-proposal `accept` via branch-service `deployProposal`

**Status**: Needs live probe — endpoint known, request body type-erased
**Priority**: High — the Global Proposal merge path; biggest remaining ontology-workflow gap
**Found**: 2026-07-27 parity swarm (agent-16)

## Summary

The published `@palantir/branch-service-api` client (complete source in the
`@palantir/mcp@0.408.0` esbuild sourcemap, extracted to `/tmp/mcp-inspect/`)
contains the deployment operations that move a Global Proposal to its
terminal state. Palantir's own `viewProposalTool` confirms `DEPLOYED`
("merged to main") is the terminal state for an approved proposal. This is
the accept/merge semantic the CLI fails closed today.

## Evidence

From the complete published `BranchService` client (23 methods, no
tree-shaking in esbuild — this is the full class):

- Preflight: `checkProposalDeployable` —
  `PUT branch-service/api/branch/check-deployable/branch/{branchRid}/proposal/{proposalRid}`
- Deploy: `deployProposal` —
  `POST branch-service/api/branch/deploy-proposal/branch/{branchRid}/proposal/{proposalRid}`
- Supporting: `getDeploymentRecord`, `getDeploymentHistory`,
  `abortDeployment` (exact paths in the sourcemap)
- Also present: `updateProposal` —
  `PUT branch-service/api/branch/proposal/update/{proposalRid}`

Existing verified sibling routes in `src/foundry_cli/services/global_branching.py`
(proposal load :455, create :555, close :589) — same `FoundryInternalClient`
pattern, same service base path.

**Caveat**: request bodies are type-erased in the esbuild bundle — the body
shape (possibly empty, possibly a options object) cannot be recovered from
the published client. Live probing is mandatory before implementation.

## Work items (after verification)

1. `GlobalProposalService.check_deployable` (read-only preflight) — safe to
   implement first; even an unverified-body probe is non-mutating.
2. `GlobalProposalService.deploy_proposal_plan` / `deploy_proposal`
   (plan-first, `--apply --yes`, destructive risk class).
3. Wire `foundry proposal accept global-proposal` to deploy; update
   `SDK_REACHABLE_CAPABILITIES` and `UNSUPPORTED_CAPABILITY_REASONS`.
4. Delegation + service tests in the existing mocking style.
5. Docs: `reference/proposal-commands.md`,
   `reference/global-branching-commands.md`, `workflows/proposal-review.md`,
   `workflows/ontology-authoring.md` (publication order final step).
6. CHANGELOG entry.

## Live verification plan

Against a disposable ontology branch + proposal on a live deployment:

1. Create disposable branch (`global-branch create`) and proposal
   (`global-proposal create`).
2. Run `check-deployable` — non-mutating; record response shape.
3. Strict-deserialization probes on deploy: bogus-RID bodies must 400/404
   (not 403) to prove routing and body parsing.
4. Deploy the disposable proposal; read back via `global-proposal get` and
   confirm terminal state; confirm `getDeploymentRecord` reflects it.
5. Record the verified contract in the service docstring, matching the
   evidence-comment style at `global_branching.py:1-43`.

## Acceptance criteria

- `foundry proposal accept global-proposal <rid>` works end-to-end on a live
  deployment, plan-first with double confirmation.
- Preflight exposed (e.g. `foundry global-proposal check-deployable` or as a
  plan-stage step) and used before deploy.
- Tests green; drift check clean; CHANGELOG updated.

## Out of scope

- `updateProposal` and deployment history/abort — note availability in the
  service docstring; implement only if a concrete need appears.
- Proposal `approve` — evidence of absence: Palantir's MCP routes approval
  to the UI (`/workspace/developer-branching/proposal/{rid}`); keep
  fail-closed.
