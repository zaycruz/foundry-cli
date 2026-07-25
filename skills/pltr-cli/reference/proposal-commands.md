# Proposal Commands

Review-workflow operations on proposals (for example code-repository pull
requests). Coverage depends on the pinned `foundry-platform-sdk`: when the
pinned client does not expose an operation for the selected proposal type,
the command returns an explicit `unsupported-capability` result instead of
guessing. (For Ontology Global Proposals backed by branch-service, see
`global-branching-commands.md`.)

## Read Commands

```bash
# Get one proposal
pltr proposal get PROPOSAL_TYPE PROPOSAL_ID [--parent-rid RID] [--format FORMAT]

# List proposals under a parent (when supported for the type)
pltr proposal list PROPOSAL_TYPE PARENT_RID [--format FORMAT]

# Examples
pltr proposal get code-repository 123 --parent-rid ri.stemma.main.repository.abc123
pltr proposal list code-repository ri.stemma.main.repository.abc123
```

## Write Commands

```bash
# Create a proposal (when the pinned client exposes the operation)
pltr proposal create PROPOSAL_TYPE --parent-rid RID \
    [--title TITLE] [--source-ref REF] [--target-ref REF] [--description TEXT]

# Comment on a proposal
pltr proposal comment PROPOSAL_TYPE PROPOSAL_ID MESSAGE [--parent-rid RID]

# Review actions (return unsupported-capability when not exposed)
pltr proposal approve PROPOSAL_TYPE PROPOSAL_ID [--parent-rid RID] [--message TEXT]
pltr proposal request-changes PROPOSAL_TYPE PROPOSAL_ID [--parent-rid RID] [--message TEXT]
pltr proposal accept PROPOSAL_TYPE PROPOSAL_ID [--parent-rid RID] [--yes]

# Merge a code PR (or unsupported-capability)
pltr proposal merge PROPOSAL_TYPE PROPOSAL_ID [--parent-rid RID] [--yes]

# Refresh and close after explicit confirmation
pltr proposal close PROPOSAL_TYPE PROPOSAL_ID [--parent-rid RID] [--yes]

# Examples
pltr proposal comment code-repository 123 "looks good" \
    --parent-rid ri.stemma.main.repository.abc123
pltr proposal merge code-repository 123 \
    --parent-rid ri.stemma.main.repository.abc123 --yes
```
