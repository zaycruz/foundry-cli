# Global Branching Commands

Ontology Global Branch and Global Proposal operations, backed by the
internal `branch-service` API. There are no list endpoints; load-by-RID
only. Success response shapes are UNVERIFIED on a live Foundry deployment (branch-service
is enabled but unused there) and are passed through raw.

Write commands are plan-first: they print a dry-run plan by default and
issue no network request. A real mutation requires `--apply`; destructive
closes additionally require `--yes`. The create contracts could not be
verified end-to-end (2026-07-24 validation, `the captured contract`),
so `create --apply` refuses with an `unverified-write-contract` error instead
of guessing a request body. The close contracts are verified (empty-body
writes with a contract-verified error contract), so `close --apply --yes` sends.

## Global Branch Commands

### Get Global Branch

```bash
pltr global-branch get BRANCH_RID [--format FORMAT]

# Example
pltr global-branch get ri.global-branch.main.branch.abc123
```

### Create Global Branch (plan-first; --apply currently blocked)

```bash
pltr global-branch create DISPLAY_NAME \
    [--ontology-rid ONTOLOGY_RID] [--description TEXT] [--apply] [--format FORMAT]

# Backed by branch-service POST /branch/create. 2026-07-24 contract-recovery
# validation on a live Foundry deployment identified the request fields {displayName,
# description, ontologyRid} but the request never progressed past
# 400 Default:InvalidArgument -- the contract is NOT verified end-to-end, so
# --apply refuses rather than guessing. Without --apply the command prints
# the dry-run plan and issues no network request.

# Example
pltr global-branch create "My Branch" --ontology-rid ri.ontology.main.ontology.abc123
```

### Close Global Branch (DESTRUCTIVE; plan-first)

```bash
pltr global-branch close BRANCH_RID [--apply] [--yes] [--format FORMAT]

# Backed by branch-service PUT /branch/close/{branchRid} (empty-body write;
# error contract contract-verified, success shape UNVERIFIED and
# passed through raw). Without --apply the command prints the dry-run plan
# and issues no network request. The real close requires both --apply and
# --yes.

# Example
pltr global-branch close ri.global-branch.main.branch.abc123 --apply --yes
```

## Global Proposal Commands

### Get Global Proposal

```bash
pltr global-proposal get PROPOSAL_RID [--format FORMAT]

# Example
pltr global-proposal get ri.global-proposal.main.proposal.abc123
```

### Create Global Proposal (plan-first; --apply currently blocked)

```bash
pltr global-proposal create DISPLAY_NAME \
    [--branch-rid BRANCH_RID] [--description TEXT] [--apply] [--format FORMAT]

# Backed by branch-service POST /branch/proposal/create. 2026-07-24
# contract-recovery validation identified the request fields {branchRid,
# description, displayName} but the request never progressed past
# 400 Default:InvalidArgument -- the contract is NOT verified end-to-end,
# so --apply refuses rather than guessing. Without --apply the command
# prints the dry-run plan and issues no network request.

# Example
pltr global-proposal create "My Proposal" --branch-rid ri.global-branch.main.branch.abc123
```

### Close Global Proposal (DESTRUCTIVE; plan-first)

```bash
pltr global-proposal close PROPOSAL_RID [--apply] [--yes] [--format FORMAT]

# Backed by branch-service PUT /branch/proposal/close/{proposalRid}
# (empty-body write; error contract contract-verified, success shape
# UNVERIFIED and passed through raw). Without --apply the command prints
# the dry-run plan and issues no network request. The real close requires
# both --apply and --yes.

# Example
pltr global-proposal close ri.global-proposal.main.proposal.abc123 --apply --yes
```
