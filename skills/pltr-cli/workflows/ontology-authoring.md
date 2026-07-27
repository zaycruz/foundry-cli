# Ontology Schema Authoring Workflow

Use this workflow when creating, evolving, or deleting ontology object types, link types, or action types, including work staged on an Ontology Global Branch and shipped through a Global Proposal. Every mutating command is plan-first: the default is a dry-run plan and no Foundry resource changes without `--apply` (plus `--yes` for deletes).

## Contract

This workflow guarantees that the agent:

- assesses the intended schema change with `pltr dependency` before any mutation and retains the baseline graph artifact;
- discovers the current ontology state read-only before authoring;
- authors through `modifyOntology` commands in the required publication order, dry-run first;
- stages work on a Global Branch and ships it through a Global Proposal, both plan-first;
- reruns the same dependency target after the change and gates on the `--compare-artifact` diff.

It does not approve or merge a proposal, and it never passes `--apply` or `--yes` without an explicit operator decision.

## Phase 1: Run the pre-change dependency gate

Follow `workflows/change-impact-assessment.md`. Select the narrowest existing target the change touches and capture the baseline with an explicit change description:

```bash
pltr dependency object-type "$ONTOLOGY_RID" "$OBJECT_TYPE" \
  --profile "$PROFILE" \
  --branch "$BRANCH" \
  --change "add property capacity to Cohort" \
  --change-type optional-to-required \
  --output-mode agent \
  --format json \
  --graph-output ./ontology-change-baseline.json \
  --output ./ontology-change-agent.json
```

Use the target matching the change: `pltr dependency object-type` for object type and property work, `pltr dependency link-type ONTOLOGY_RID OBJECT_TYPE LINK_TYPE` for link types, `pltr dependency action-type ONTOLOGY_RID ACTION_TYPE` for action types. Use `--change-type remove-delete` for deletes and `action-input-change` for action parameter changes.

For a net-new type that does not exist yet, the narrowest target is undiscoverable. Run the gate against the closest existing neighbor (the object types the new link type will connect, or `pltr dependency resource` on the backing dataset) and record the substitution as a coverage gap. Do not skip the gate because the target is new.

Resolve `must_verify_before_merge` items before applying anything, or obtain explicit operator acceptance.

## Phase 2: Discover the current ontology state

Read-only discovery. Resolve the ontology RID, then enumerate what exists:

```bash
# Resolve the ontology RID for this stack (fails loudly on zero or many)
pltr ontology rid --profile "$PROFILE"

# Or list and pick explicitly
pltr ontology list --profile "$PROFILE" --format json

# Inspect the ontology and its object types
pltr ontology get "$ONTOLOGY_RID" --profile "$PROFILE"
pltr ontology object-type-list "$ONTOLOGY_RID" --profile "$PROFILE" --format json

# Read the specific types the change touches
pltr ontology object-type-get "$ONTOLOGY_RID" Cohort --profile "$PROFILE"
pltr ontology link-type-get "$ONTOLOGY_RID" Cohort members --profile "$PROFILE"
pltr ontology action-type-get "$ONTOLOGY_RID" create-cohort --profile "$PROFILE"
```

Resolve identifiers to RIDs and internal IDs before authoring. Link type upserts and object/link type deletes take internal IDs (for example `ns0abcde.cohort`), not API names:

```bash
pltr ontology resolve "$ONTOLOGY_RID" --kind object-type --api-name Cohort --profile "$PROFILE"
pltr ontology resolve "$ONTOLOGY_RID" --kind property --object-type Cohort --api-name capacity --profile "$PROFILE"
pltr ontology resolve "$ONTOLOGY_RID" --kind action-type --api-name create-cohort --profile "$PROFILE"
```

## Phase 3: Author object types and properties

Steps 1-2 of the required publication order (backing dataset schema, transaction functions) are outside `pltr ontology`; confirm they are done first. Then run the dry-run plan, review it, and only then apply:

```bash
# Dry-run plan (default; nothing is written)
pltr ontology object-type-upsert "$ONTOLOGY_RID" \
  --api-name Cohort \
  --display-name "Cohort" \
  --primary-key cohortId \
  --backing-dataset ri.foundry.main.dataset.abc123 \
  --profile "$PROFILE"

# Apply only after the plan and the Phase 1 gate are reviewed
pltr ontology object-type-upsert "$ONTOLOGY_RID" \
  --api-name Cohort \
  --display-name "Cohort" \
  --primary-key cohortId \
  --backing-dataset ri.foundry.main.dataset.abc123 \
  --profile "$PROFILE" \
  --apply
```

When the object type already exists, the upsert switches to the update path and merges display name and description; primary key and backing dataset must match the existing type. Other field-level object type updates are not exposed — document the gap instead of attempting delete-and-recreate.

Add properties to an existing object type with the backing column mapping (the column must already exist in the dataset schema):

```bash
pltr ontology object-type-add-property "$ONTOLOGY_RID" \
  --object-type Cohort \
  --api-name capacity \
  --type INTEGER \
  --backing-column capacity \
  --profile "$PROFILE"
# then re-run with --apply
```

Deletes are destructive and run in reverse publication order — dependent action types and link types first. The delete target is the internal ObjectTypeId from Phase 2, and the real delete requires both flags:

```bash
pltr ontology object-type-delete "$ONTOLOGY_RID" ns0abcde.cohort \
  --profile "$PROFILE" --apply --yes
```

## Phase 4: Author link types

Step 4 of the publication order; both object types must already exist. `--from-object-type-id` and `--to-object-type-id` take internal ObjectTypeIds from `pltr ontology resolve`:

```bash
# Dry-run plan
pltr ontology link-type-upsert "$ONTOLOGY_RID" \
  --api-name members \
  --from-object-type-id ns0abcde.cohort \
  --to-object-type-id ns0abcde.person \
  --many-side-property cohortId \
  --profile "$PROFILE"
# then re-run with --apply
```

Existing link types are not updated; the create validation reports that case explicitly. Deletes take the internal LinkTypeId and require `--apply --yes`:

```bash
pltr ontology link-type-delete "$ONTOLOGY_RID" ns0abcde.members \
  --profile "$PROFILE" --apply --yes
```

## Phase 5: Author action types

Step 5 of the publication order; referenced object types and link types must exist. Create from an ActionTypeCreate JSON document (`--definition` takes a file path, or `-` for stdin):

```bash
# Dry-run plan, then apply
pltr ontology action-type-upsert "$ONTOLOGY_RID" \
  --definition action-type.json \
  --profile "$PROFILE"
pltr ontology action-type-upsert "$ONTOLOGY_RID" \
  --definition action-type.json \
  --profile "$PROFILE" --apply
```

Evolve an existing action type with a partial patch (`logic`, `parameters`, `validations`, `writeAuthorization`, `status`, `displayMetadata`; unknown keys fail loudly):

```bash
pltr ontology action-type-update "$ONTOLOGY_RID" \
  --action-type create-cohort \
  --definition patch.json \
  --profile "$PROFILE"
# then re-run with --apply
```

Delete by API name, first in reverse publication order:

```bash
pltr ontology action-type-delete "$ONTOLOGY_RID" create-cohort \
  --profile "$PROFILE" --apply --yes
```

Finish with step 6: validate each touched action without executing it.

```bash
pltr ontology action-validate "$ONTOLOGY_RID" create-cohort \
  '{"cohortId": "test-cohort"}' --profile "$PROFILE"
```

Steps 7-8 (regenerate OSDK, enable application controls) are outside this CLI; record them as follow-up work.

## Phase 6: Stage work on a Global Branch

Global Branch RIDs use a double dot: `ri.branch..branch.<uuid>`. There are no list endpoints; load-by-RID only. Create is plan-first:

```bash
# Dry-run plan (no network request), then apply
pltr global-branch create "Cohort capacity change" \
  --ontology-rid "$ONTOLOGY_RID" \
  --description "Add capacity property and create-cohort action" \
  --profile "$PROFILE"
pltr global-branch create "Cohort capacity change" \
  --ontology-rid "$ONTOLOGY_RID" \
  --profile "$PROFILE" --apply

# Load the branch back by RID
pltr global-branch get ri.branch..branch.00000000-0000-0000-0000-000000000024 \
  --profile "$PROFILE"
```

Known capability gaps — document them, do not guess:

- Of the `modifyOntology` authoring commands, only `object-type-add-property` and `action-type-update` accept `--branch-rid`. `object-type-upsert`, `link-type-upsert`, and `action-type-upsert` have no branch targeting flag; writes from them land on the default branch.
- Whether a Global Branch RID (`ri.branch..branch.*`) is accepted as the `ontologyBranchRid` of `--branch-rid` is not contract-verified. Verify on a non-production stack before relying on it.
- Closing a branch is destructive: `pltr global-branch close BRANCH_RID --apply --yes`.

## Phase 7: Ship through a Global Proposal

Create the proposal against the branch, plan-first. `--merge-to main` is the default; a global branch RID targets another branch:

```bash
# Dry-run plan, then apply
pltr global-proposal create "Ship cohort capacity" \
  --branch-rid ri.branch..branch.00000000-0000-0000-0000-000000000024 \
  --merge-to main \
  --profile "$PROFILE"
pltr global-proposal create "Ship cohort capacity" \
  --branch-rid ri.branch..branch.00000000-0000-0000-0000-000000000024 \
  --profile "$PROFILE" --apply

# Load the proposal back by RID
pltr global-proposal get ri.branch..proposal.00000000-0000-0000-0000-000000000025 \
  --profile "$PROFILE"
```

There is no CLI command to approve or merge a proposal; the merge step happens in Foundry outside this workflow. `pltr global-proposal close PROPOSAL_RID --apply --yes` closes without merging and is destructive — confirm with the operator which outcome is intended before running it.

## Phase 8: Run the post-change comparison gate

After the change is applied (and after the proposal merges, for shipped work), rerun the identical dependency command from Phase 1 — same target, profile, branch, direction, depth, and budgets — with `--compare-artifact` against the retained baseline:

```bash
pltr dependency object-type "$ONTOLOGY_RID" "$OBJECT_TYPE" \
  --profile "$PROFILE" \
  --branch "$BRANCH" \
  --change "add property capacity to Cohort" \
  --change-type optional-to-required \
  --output-mode ci \
  --compare-artifact ./ontology-change-baseline.json \
  --graph-output ./ontology-change-after.json
```

Exit contract: `0` clean, `2` needs verification, `1` fatal failure. Review added edges, removed edges, and changed coverage. A removed edge is not a verified deletion when the run was budget-truncated or coverage-incomplete. Exit `2` blocks merge or deployment until the verification items are resolved or explicitly accepted by the operator.

## Output Format

Report:

1. intended schema change and target (object type, link type, or action type);
2. pre-change gate status, blast-radius score, and baseline artifact path;
3. dry-run plan summary for each authoring command, in publication order;
4. what was applied, with the branch and proposal RIDs when staged;
5. capability gaps hit (untargetable branches, unsupported updates, merge step);
6. validation results (`action-validate`) and remaining publication steps 7-8;
7. post-change diff result and CI exit code.

## Anti-Patterns

- Running any authoring command with `--apply` before reviewing its dry-run plan
- Skipping the Phase 1 gate because the object type is net-new
- Authoring out of publication order (action types before their object and link types exist)
- Deleting an object type before its dependent action types and link types
- Passing API names where a command takes an internal ID (`object-type-delete`, `link-type-upsert`, `link-type-delete`)
- Assuming an upsert updates an existing link type or action type (creates only; use `action-type-update` for action types)
- Assuming `--branch-rid` targets a Global Branch without verification, or expecting branch targeting on upserts that do not expose it
- Treating `global-proposal close` as a merge
- Discarding the baseline artifact after reading the compact agent block
- Treating a budget-truncated comparison as proof a dependency was removed
