# TICKET-001: Implement code-pr `approve` / `request-changes` via stemma `reviewPullRequest`

**Status**: Ready for contract extraction
**Priority**: High — strongest lead; unblocks 2 of the 9 fail-closed proposal actions
**Found**: 2026-07-27 parity swarm (agent-16)

## Summary

The published stemma client inside `@palantir/mcp@0.408.0` contains
`reviewPullRequest` and `batchReviewPullRequests` — the review-verdict
operations the CLI currently fails closed. The npm-cache tarball's esbuild
sourcemap holds the complete verbatim client source (extracted to
`/tmp/mcp-inspect/` by the investigation; re-extract if purged).

## Evidence

- Endpoint: `PUT stemma-pull-request/api/pulls/{pullRequestRid}/review`
  (from the generated client in the sourcemap; confirm exact path and body
  during extraction).
- Same evidence class that justified the branch-service implementation
  (`src/foundry_cli/services/global_branching.py:1-43`): Palantir's own published
  client code. Repo standard additionally requires live exercise before
  shipping as a working command.
- Current fail-closed site: `src/foundry_cli/services/proposal.py`
  (`UNSUPPORTED_CAPABILITY_REASONS`, code-pr approve / request-changes).
- Existing verified sibling routes in `src/foundry_cli/services/repository.py`
  (list :136-140, get :194-196, create :341-345, comment :400-404,
  close :524-528) — the new route follows the identical
  `FoundryInternalClient.conjure()` pattern.

## Work items

1. Extract the `reviewPullRequest` request/response types from the sourcemap:
   verdict enum values (expected something like `APPROVE` / `REQUEST_CHANGES`),
   optional comment/message field, response shape.
2. Add `RepositoryService.review_pull_request_plan` / `review_pull_request`
   following the existing plan-then-execute pattern
   (`create_pull_request_plan`/`create_pull_request` at repository.py:269-359).
3. Wire the unified group: `foundry proposal approve code-pr` and
   `foundry proposal request-changes code-pr` delegate to it; dry-run plan by
   default, `--apply` to execute (mirroring the patched create/comment).
4. Move both pairs from `UNSUPPORTED_CAPABILITY_REASONS` into
   `SDK_REACHABLE_CAPABILITIES`; keep reasons map accurate for what remains.
5. Tests: delegation tests in `tests/test_services/test_proposal.py` and
   `tests/test_commands/test_proposal.py` matching the existing mocking style;
   service-level tests mirroring the pull-request comment tests.
6. Docs: update `skills/foundry-cli/reference/proposal-commands.md` and
   `workflows/proposal-review.md` (the latter is stale — it claims every
   `foundry proposal` action is fail-closed, flagged again by the swarm).

## Live verification plan (required before shipping)

Against a disposable PR on a live deployment:

1. Strict-deserialization probes: bogus-RID body must 400 (not 403) to prove
   the body shape is being parsed.
2. Real verdict on a disposable PR: `approve`, read back via
   `foundry repository pull-request get` and confirm the review state; repeat
   for `request-changes`.
3. Record evidence in the service docstring, same style as
   `global_branching.py`'s contract comments.

## Acceptance criteria

- `foundry proposal approve code-pr <rid>` and `request-changes code-pr <rid>`
  work end-to-end on a live deployment, plan-first.
- `uv run pytest tests/ -q` green; `check_skill_command_drift.py` no drift
  (no new command paths, behavior only).
- CHANGELOG entry under Unreleased.

## Out of scope

- `batchReviewPullRequests` (no CLI use case yet; note in service docstring).
- code-pr `merge` — tracked separately in TICKET-002.
