# TICKET-002: Verify code-pr `merge` — status-transition hypothesis

**Status**: Needs live probe (hypothesis only — do NOT implement from this alone)
**Priority**: Medium — completes the code-pr lifecycle
**Found**: 2026-07-27 parity swarm (agent-15)

## Summary

Two unverified hypotheses for merging a code PR headlessly. Neither is
evidence; this ticket exists to kill or confirm them safely.

## Hypotheses

1. **Status transition via the verified update route.**
   `PUT stemma-pull-request/api/pulls/{rid}/update` with
   `{"title": ..., "status": "MERGED"}`. The close implementation
   (`repository.py:524-528`) only ever probed `status: "CLOSED"`
   (probes at repository.py:433-444), and the PR read-back object carries a
   `merged` field — so a merge transition through the same route is plausible.
2. **UI capture.** Watch the Merge button in Code Repositories on a live
   deployment (browser devtools) and record the exact request, whether it
   lands on `stemma-pull-request` or another service.

Explicitly rejected: pushing to the verified git smart-HTTP endpoint
`/stemma/git/{rid}` — that bypasses the PR and is not a PR merge.

## Evidence against guessing

- SDK `foundry_sdk` v1/v2 contains no stemma/code-repositories module at all.
- The official MCP exposes no approve/merge tool either
  (`capabilities.py:309-336` tracks only create/list/get/comment), so no MCP
  client contract to recover — unlike TICKET-001.
- The only SDK tokens (`CODE_REPOSITORY_MERGE_PULL_REQUEST` in
  `v2/checkpoints/models.py:94-95`) are audit-event enums, not endpoints.

## Live verification plan

This is a real merge mutation — requires an approved disposable-PR test plan:

1. Create a disposable repository + PR on a live deployment.
2. UI capture first (non-destructive): record the Merge request verbatim.
3. If the UI route matches hypothesis 1, probe on the disposable PR:
   `PUT /pulls/{rid}/update` with `{"title": <unchanged>, "status": "MERGED"}`.
4. Read back via `foundry repository pull-request get`; confirm `merged` state
   and that the target branch advanced.
5. Record the verified contract (or the killed hypothesis) in the service
   docstring.

## If confirmed — implementation

- `RepositoryService.merge_pull_request_plan` / `merge_pull_request`
  (plan-first, `--apply --yes`, destructive risk class).
- Wire `foundry proposal merge code-pr`; update `SDK_REACHABLE_CAPABILITIES`
  and reasons map; delegation tests; docs; CHANGELOG.

## Acceptance criteria

- Hypothesis 1 confirmed or killed with recorded evidence.
- If confirmed: `foundry proposal merge code-pr <rid>` works end-to-end,
  plan-first with double confirmation, tests green.

## Out of scope

- Merge-queue semantics, approval-policy enforcement (server-side concern;
  surface server rejections as typed errors, do not pre-validate).
