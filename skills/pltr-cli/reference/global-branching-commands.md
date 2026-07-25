# Global Branching Commands

Ontology Global Branch and Global Proposal operations, backed by the
internal `branch-service` API. There are no list endpoints; load-by-RID
only. All contracts (loads, creates, closes) were verified end-to-end on
a live Foundry deployment 2026-07-25 — request/response shapes derived from
`@palantir/mcp` client contract (`the captured contract`)
and confirmed by a live create→load→proposal→close→close run
(`the captured contract`).
The `mergeTo` union arms and `resourcesToAdd` element shape were verified
separately (`the captured contract`).

Write commands are plan-first: they print a dry-run plan by default and
issue no network request. A real mutation requires `--apply`; destructive
closes additionally require `--yes`.

RID formats (note the DOUBLE DOT — empty service segment):

- Global Branch: `ri.branch..branch.<uuid>`
- Global Proposal: `ri.branch..proposal.<uuid>`

## Global Branch Commands

### Get Global Branch

```bash
pltr global-branch get BRANCH_RID [--format FORMAT]

# Backed by branch-service PUT /branch/load/{branchRid} (empty-body load).
# Success response is {"branchRecord": {...}} (contract-verified),
# passed through raw.

# Example
pltr global-branch get ri.branch..branch.00000000-0000-0000-0000-000000000024
```

### Create Global Branch (plan-first; --apply issues the real mutation)

```bash
pltr global-branch create DISPLAY_NAME \
    [--ontology-rid ONTOLOGY_RID] [--description TEXT] \
    [--add-resource RESOURCE_RID]... [--apply] [--format FORMAT]

# Backed by branch-service POST /branch/create (contract-verified).
# The command first resolves the ontology's compassNamespaceRid via
# POST /ontology-metadata/api/ontology/v2/load/all (body
# {"externalMappingConfigurationFilters": []}, read
# ontologies[ontologyRid].compassNamespaceRid), then sends
# {description, displayName, ontologyRid, resourcesToAdd: [],
#  compassNamespaceRid} and returns the new branch RID
# (branchRecord.branchRid, ri.branch..branch.<uuid>). Without --apply the
# command prints the dry-run plan and issues no network request.
#
# --add-resource is repeatable; entries are sent as plain ResourceRid
# strings in resourcesToAdd (server-evidenced: object entries
# are rejected with 422 Conjure:UnprocessableEntity). The server rejects
# resources it cannot branch with a typed
# Branch:ResourcesUnableToBranchError. The default empty array is the
# fully contract-verified path.

# Example
pltr global-branch create "My Branch" \
    --ontology-rid ri.ontology.main.ontology.abc123 --apply
```

### Close Global Branch (DESTRUCTIVE; plan-first)

```bash
pltr global-branch close BRANCH_RID [--apply] [--yes] [--format FORMAT]

# Backed by branch-service PUT /branch/close/{branchRid} (empty-body write
# returning 200 {}; contract-verified). Without --apply the command
# prints the dry-run plan and issues no network request. The real close
# requires both --apply and --yes.

# Example
pltr global-branch close ri.branch..branch.00000000-0000-0000-0000-000000000024 --apply --yes
```

## Global Proposal Commands

### Get Global Proposal

```bash
pltr global-proposal get PROPOSAL_RID [--format FORMAT]

# Example
pltr global-proposal get ri.branch..proposal.00000000-0000-0000-0000-000000000025
```

### Create Global Proposal (plan-first; --apply issues the real mutation)

```bash
pltr global-proposal create DISPLAY_NAME \
    [--branch-rid BRANCH_RID] [--description TEXT] \
    [--merge-to main|BRANCH_RID] [--apply] [--format FORMAT]

# Backed by branch-service POST /branch/proposal/create (contract-verified
# 2026-07-25). Sends {branchRid, displayName, description, mergeTo} where
# mergeTo is the ProposalMergeTo Conjure union with two arms (generated
# @palantir/branch-service-api proposalMergeTo.js evidence): the default
# --merge-to main sends {"main": {}, "type": "main"} (contract-verified 200);
# a global branch RID sends {"branchRid": <rid>, "type": "branchRid"}
# (encoding server-accepted; the server validates the target semantically
# and answers a typed Branch:InvalidMergeTo when invalid). Returns the new
# proposal RID (proposal.proposalRid, ri.branch..proposal.<uuid>).
# Without --apply the command prints the dry-run plan and issues no network
# request.

# Example
pltr global-proposal create "My Proposal" \
    --branch-rid ri.branch..branch.00000000-0000-0000-0000-000000000024 --apply
```

### Close Global Proposal (DESTRUCTIVE; plan-first)

```bash
pltr global-proposal close PROPOSAL_RID [--apply] [--yes] [--format FORMAT]

# Backed by branch-service PUT /branch/proposal/close/{proposalRid}
# (empty-body write returning 200 {}; contract-verified). Without
# --apply the command prints the dry-run plan and issues no network request.
# The real close requires both --apply and --yes.

# Example
pltr global-proposal close ri.branch..proposal.00000000-0000-0000-0000-000000000025 --apply --yes
```
