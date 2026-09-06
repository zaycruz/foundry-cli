# Parity Gap Tickets

Open leads from the 2026-07-27 MCP-parity investigation (swarm findings).
Each ticket names its evidence class and the verification required before
implementation, per the repo rule: no unverified contracts, no guessed behavior.

| Ticket | Lead | Evidence class | Status |
|--------|------|----------------|--------|
| [001](TICKET-001-code-pr-review.md) | code-pr `approve` / `request-changes` via stemma `reviewPullRequest` | Published client contract (strong) | Ready for extraction |
| [002](TICKET-002-code-pr-merge.md) | code-pr `merge` via `PUT /pulls/{rid}/update` status `MERGED` | Hypothesis (weak) | Needs live probe |
| [003](TICKET-003-global-proposal-deploy.md) | global-proposal `accept` via branch-service `deployProposal` | Published client contract, body type-erased | Needs live probe |
| [004](TICKET-004-global-proposal-comment-list.md) | global-proposal `comment` / `list` | Leads only (comments service, UI endpoint) | Needs UI capture |
| [005](TICKET-005-preview-transform.md) | `preview_transform` unblock paths | Blocked upstream | Watch / needs enrollment |
| [007](TICKET-007-evaluation-suites.md) | evaluation-suite orchestration (AIP Evals) | Leads only (ruled out mcp 0.442–0.445, SDK, public v2 API) | Needs UI capture |
| [008](TICKET-008-ontology-object-writes.md) | object upserts via actions; transaction `postEdits` | Published client contract (strong) | Implemented; live verification pending |
| [009](TICKET-009-ai-fde.md) | AI FDE thread orchestration (agent loop, stop, reject, delete/rename) | UI capture complete for thread primitives (CDP 2026-09-04) | Thread primitives implemented; agent loop needs UI capture |

Evidence-class legend, matching the standard set in
`src/foundry_cli/services/global_branching.py:1-43`:

- **Published client contract**: verb + path recovered from Palantir's own
  shipped client code (`@palantir/mcp` dist / generated service APIs).
- **Contract-verified**: the above AND exercised end-to-end against a live
  deployment (typed error responses count as contract signals). Only
  contract-verified operations may ship as working commands.
