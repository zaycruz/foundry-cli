# Proposal Review and Merge Workflow

Reviewing and merging changes through Foundry proposals: code repository pull requests (internal `stemma-pull-request` API) and Ontology Global Proposals (internal `branch-service` API). Use this workflow when asked to review, approve, merge, accept, or close a proposal.

Capability reality of this install:

- The unified `pltr proposal` group works for code-pr `create`/`list`/`get`/`comment`/`close` (via `RepositoryService`) and global-proposal `create`/`get`/`close` (via `GlobalProposalService`). `create` and `comment` are dry-run plan by default; `--apply` executes.
- The type-specific groups (`pltr repository pull-request`, `pltr global-proposal`, `pltr global-branch`) expose the same operations plus extras (repository context/clone, branch management) and remain the better path for deep inspection.
- Still fail-closed with exit 6 `unsupported-capability`: code-pr `approve`/`request-changes`/`merge`, and global-proposal `list`/`comment`/`approve`/`request-changes`/`merge`/`accept`. Document these as gaps; never claim such an action succeeded. Leads for unblocking them are tracked in `tickets/`.

## Contract

This workflow guarantees that the agent:

- identifies the proposal system and locates the proposal before reviewing;
- inspects the actual changes with read-only commands and evidence, not summaries alone;
- runs a change-impact assessment before approving, merging, or accepting anything that changes a Foundry resource;
- performs every write plan-first: dry-run plan shown, explicit `--apply` (and `--yes` for destructive closes) required;
- reports unsupported capabilities as gaps instead of simulating them.

It does not fabricate approvals, merges, or accepts that the pinned client cannot perform.

## Phase 1: Identify the proposal system and locate the proposal

Code PRs are listed and addressed by pull-request RID; Global Proposals are load-by-RID only (there is no list endpoint).

```bash
# Code PRs: list across repositories (a repository RID filters client-side)
pltr repository pull-request list --profile "$PROFILE"
pltr repository pull-request list ri.stemma.main.repository.abc123 \
  --profile "$PROFILE" --format json

# Global Proposals: no list endpoint exists; the RID must come from the
# operator, the Foundry UI, or a prior create. Format note: DOUBLE DOT.
pltr global-proposal get ri.branch..proposal.00000000-0000-0000-0000-000000000025 \
  --profile "$PROFILE"
```

The unified facade works for reads (the type-specific group is still preferred for inspection depth):

```bash
pltr proposal list code-pr ri.stemma.main.repository.abc123 \
  --profile "$PROFILE" --format json
pltr proposal get code-pr 123 --parent-rid ri.stemma.main.repository.abc123
```

## Phase 2: Inspect the changes (read-only)

For a code PR, read the PR record, then the repository context, and clone for a real diff when the file tree view is not enough.

```bash
# PR metadata: title, status, author, head/base refs
pltr repository pull-request get ri.pull-request.main.pull-request.abc123 \
  --profile "$PROFILE" --format json

# Repository context: metadata, default branch, refs, file tree at a ref.
# Note: stemma silently falls back to the default branch for unresolvable
# refs -- confirm the returned ref matches what you asked for.
pltr repository context ri.stemma.main.repository.abc123 \
  --ref refs/heads/feat/x --profile "$PROFILE"

# Local inspection: plan first, then clone the head branch and diff locally
pltr repository clone ri.stemma.main.repository.abc123 ./review-abc123 --dry-run
pltr repository clone ri.stemma.main.repository.abc123 ./review-abc123 \
  --branch feat/x
git -C ./review-abc123 diff master...HEAD
```

`pltr repository clone` injects the profile bearer token via an environment-injected `http.extraHeader`; the token is never printed, never on the command line, and never persisted in the clone's config, so later fetches need fresh credentials. The clone refuses a non-empty target without `--force`.

For a Global Proposal, load the proposal and its backing branch:

```bash
pltr global-proposal get ri.branch..proposal.00000000-0000-0000-0000-000000000025 \
  --profile "$PROFILE" --format json
pltr global-branch get ri.branch..branch.00000000-0000-0000-0000-000000000024 \
  --profile "$PROFILE" --format json
```

## Phase 3: Assess change impact before any approval, merge, or accept

Merging a code PR or accepting an Ontology Global Proposal changes Foundry resources. Run `workflows/change-impact-assessment.md` against the resources the proposal touches before proceeding, and carry the baseline artifact path into the review record. A proposal that renames, retypes, or deletes ontology properties, link types, action types, or query types must clear the dependency gate first; a coverage gap in that assessment is uncertainty, not "no impact."

## Phase 4: Review actions (plan-first writes)

Commenting works on code PRs and is dry-run by default:

```bash
# Dry-run plan: prints the exact intended POST body, writes nothing
pltr repository pull-request comment ri.pull-request.main.pull-request.abc123 \
  "Transform drops null handling for order_id; see impact artifact." \
  --profile "$PROFILE"

# Real comment
pltr repository pull-request comment ri.pull-request.main.pull-request.abc123 \
  "Transform drops null handling for order_id; see impact artifact." \
  --apply --profile "$PROFILE"
```

Approve and request-changes are unsupported-capability today. Record the review verdict as a comment instead, and state plainly in the output that no formal approval was recorded:

```bash
pltr proposal approve code-pr 123 \
  --parent-rid ri.stemma.main.repository.abc123 --message "lgtm"
# -> unsupported-capability (gap; no approval recorded)
```

Closing a code PR without merging is destructive and plan-first; the PR is read first to obtain its title, and an already-CLOSED PR is reported as already-closed:

```bash
# Dry-run plan of the exact PUT body
pltr repository pull-request close ri.pull-request.main.pull-request.abc123 \
  --profile "$PROFILE"

# Real close requires both flags
pltr repository pull-request close ri.pull-request.main.pull-request.abc123 \
  --apply --yes --profile "$PROFILE"
```

## Phase 5: Merge or accept (gated; mostly unavailable)

- Code PR merge: `pltr proposal merge code-pr ... --yes` returns `unsupported-capability` today. There is no working merge command in this install; the merge must happen outside the CLI (Foundry UI). Report this gap; do not treat a close as a merge.
- Global Proposal accept: `pltr proposal accept global-proposal ... --yes` returns `unsupported-capability` today. Same rule.

When a merge or accept happened outside the CLI, verify the result by re-reading the PR or proposal state before reporting completion.

## Phase 6: Close a Global Proposal (destructive)

Closing a Global Proposal discards it without merging. Plan-first; the real close requires both `--apply` and `--yes`:

```bash
# Dry-run plan, no network request
pltr global-proposal close ri.branch..proposal.00000000-0000-0000-0000-000000000025 \
  --profile "$PROFILE"

# Real close
pltr global-proposal close ri.branch..proposal.00000000-0000-0000-0000-000000000025 \
  --apply --yes --profile "$PROFILE"
```

The unified `pltr proposal close` facade returns `unsupported-capability`; use the type-specific command above.

## Output Format

Report:

1. proposal system, RID, title, status, and source/target refs;
2. evidence inspected (PR record, repository context ref, local diff, branch record);
3. change-impact assessment result and baseline artifact path (when Phase 3 applied);
4. review verdict and where it was recorded (comment RID, or explicit "no formal approval possible");
5. merge/accept outcome, including unsupported-capability gaps and any out-of-band action;
6. close outcome, or confirmation that the proposal was left open.

## Anti-Patterns

- Merging or closing before running the change-impact gate
- Claiming an approval, merge, or accept succeeded when the command returned `unsupported-capability`
- Using `pltr proposal close` or `pltr repository pull-request close` as a substitute for a merge
- Skipping the dry-run plan and going straight to `--apply` / `--apply --yes`
- Treating a closed PR or proposal as merged; close discards
- Guessing a Global Proposal RID because no list endpoint exists; obtain the real RID first
- Trusting the file tree from `repository context --ref` without confirming the returned ref (stemma falls back to the default branch silently)
- Inventing proposal types; valid types are `code-pr` and `global-proposal`
- Re-running a destructive close without re-reading current state first
