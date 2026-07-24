# Global Branching Commands

Read-only Ontology Global Branch and Global Proposal inspection, backed by
the internal `branch-service` API. There are no list endpoints; load-by-RID
only. Success response shapes are UNVERIFIED on a live Foundry deployment (branch-service
is enabled but unused there) and are passed through raw.

## Global Branch Commands

### Get Global Branch

```bash
pltr global-branch get BRANCH_RID [--format FORMAT]

# Example
pltr global-branch get ri.global-branch.main.branch.abc123
```

## Global Proposal Commands

### Get Global Proposal

```bash
pltr global-proposal get PROPOSAL_RID [--format FORMAT]

# Example
pltr global-proposal get ri.global-proposal.main.proposal.abc123
```
