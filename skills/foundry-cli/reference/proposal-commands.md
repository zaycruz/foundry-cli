# Proposal Commands

Review-workflow operations on proposals. The PROPOSAL_TYPE argument selects
one of two proposal systems:

- `code-pr` — code repository pull requests, delegated to
  `RepositoryService` (internal `stemma-pull-request` API).
- `global-proposal` — Ontology Global Proposals, delegated to
  `GlobalProposalService` (internal `branch-service` API). (For the
  underlying branch surface, see `global-branching-commands.md`.)

No other type value is accepted — an unknown type is a `validation` error
(exit 4). Actions with no contract-verified implementation fail closed with
an explicit `unsupported-capability` error (exit 6) instead of guessing;
no raw endpoint fallback is attempted. All commands accept `--profile/-p`
and `--format/-f` (table, json, csv; default table).

## What Works and What Does Not

Working:

- code-pr: `create`, `list`, `get`, `comment`, `close`
- global-proposal: `create`, `get`, `close`

Still fail-closed (exit 6 `unsupported-capability`):

- code-pr: `approve`, `request-changes`, `merge` — the internal
  stemma-pull-request API has no contract-verified operations for these.
- global-proposal: `list` — the branch-service API has no proposal list
  endpoint (load-by-RID only); plus `comment`, `approve`,
  `request-changes`, `merge`, `accept` — no contract-verified operations.

The unsupported commands still parse their documented flags, but always
return the unsupported-capability error for the selected type.

## Read Commands

```bash
# Get one proposal (both types; loads by RID, --parent-rid is not needed)
pfoundry proposal get PROPOSAL_TYPE PROPOSAL_ID [--parent-rid RID] [--format FORMAT]

# List proposals (code-pr only; filtered to PARENT_RID client-side)
pfoundry proposal list code-pr PARENT_RID [--format FORMAT]

# Examples
pfoundry proposal get code-pr ri.stemma.main.pull-request.abc123
pfoundry proposal list code-pr ri.stemma.main.repository.abc123
pfoundry proposal get global-proposal ri.branch..proposal.abc123
```

## Write Commands

```bash
# Create a proposal (dry-run plan by default; --apply issues the real write)
# --parent-rid, --title and --source-ref are required
pfoundry proposal create PROPOSAL_TYPE --parent-rid RID --title TITLE \
    --source-ref REF [--target-ref REF] [--description TEXT] [--apply]

# Comment on a proposal (code-pr only; dry-run plan by default)
pfoundry proposal comment code-pr PROPOSAL_ID MESSAGE [--apply]

# Review actions (unsupported-capability, exit 6, for both types)
pfoundry proposal approve PROPOSAL_TYPE PROPOSAL_ID [--parent-rid RID] [--message TEXT]
pfoundry proposal request-changes PROPOSAL_TYPE PROPOSAL_ID [--parent-rid RID] [--message TEXT]

# Merge / accept (unsupported-capability, exit 6, for both types)
pfoundry proposal merge PROPOSAL_TYPE PROPOSAL_ID [--parent-rid RID] [--yes]
pfoundry proposal accept PROPOSAL_TYPE PROPOSAL_ID [--parent-rid RID] [--yes]

# Refresh and close after explicit confirmation (both types)
pfoundry proposal close PROPOSAL_TYPE PROPOSAL_ID [--parent-rid RID] [--yes]

# Examples
pfoundry proposal create code-pr --parent-rid ri.stemma.main.repository.abc123 \
    --title "Fix typo" --source-ref my-branch --apply
pfoundry proposal create global-proposal --parent-rid ri.ontology.main.ontology.abc123 \
    --title "Schema update" --source-ref ri.branch..branch.def456 --apply
pfoundry proposal comment code-pr ri.stemma.main.pull-request.abc123 "looks good" --apply
pfoundry proposal close code-pr ri.stemma.main.pull-request.abc123 --yes
pfoundry proposal close global-proposal ri.branch..proposal.abc123 --yes
```

`create` argument mapping differs per type:

- code-pr: `--parent-rid` is the base repository RID, `--source-ref` the
  head commitish, `--target-ref` the base branch (default
  `refs/heads/master`).
- global-proposal: `--source-ref` is the Global Branch RID the proposal
  belongs to, `--target-ref` maps to the merge target (default `main`).
  `--parent-rid` is accepted but unused — the branch RID already carries
  the target.

`close` refreshes the proposal via `get`, then asks for interactive
confirmation unless `--yes` is given; cancelling aborts with a validation
error. With `--format json`, `--yes` is required so output stays JSON-only
(validation error, exit 4, otherwise).
