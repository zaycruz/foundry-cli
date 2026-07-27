# TICKET-005: Unblock `preview_transform` (long-term watch)

**Status**: Blocked upstream — watch and revisit
**Priority**: Medium — the MCP's flagship agent workflow; the only catalog gap
**Found**: re-confirmed 2026-07-27 parity swarm (agent-14)

## Summary

`preview_transform` (run a Python transform on a sample without committing,
iterate until green) is the single blocked capability in
`src/pltr/capabilities.py:917-925`. Two independent investigations have
confirmed there is no implementable contract today.

## Why it is blocked (evidence recap)

- Not a cataloged tool: zero occurrences of "preview" in the official
  available-tools catalog; it appears only on the MCP overview page as a
  workflow description.
- Not in the shipped client: `@palantir/mcp@0.408.0` — the dist that yielded
  every other recovered contract — contains no preview_transform code.
- SDK: `foundry-platform-sdk==1.95.0` orchestration module exposes exactly
  Build/Job/Schedule/ScheduleRun/ScheduleVersion; every `preview` token is
  the `PreviewMode` feature gate, not a dry-run.
- Prior live probe (commit `d507354`, 0.28.0): the likely backing gate
  (`local-dev-access` preview) is mounted on a live deployment but returns
  **empty grants** for the CLI's token — feature enrollment or specific
  permissions appear required.
- Docs page describes only the Code Repositories Preview button
  (https://www.palantir.com/docs/foundry/code-repositories/preview-transforms/).

## Unblock paths (in preference order)

1. **Watch newer `@palantir/mcp` dists.** Palantir ships MCP updates via the
   Foundry internal npm registry. When a dist ships preview_transform, recover
   the client contract exactly as done for branch-service and stemma.
   Action: on each CLI release cycle, pull the newest dist and diff its
   tool list against `_TOOL_ROWS` / `_WORKFLOW_ROWS`.
2. **Enrollment + UI capture.** Obtain a token with a non-empty
   `local-dev-access` preview grant (requires Foundry enrollment/feature
   flag), capture the Preview button's network calls (verb, path, body,
   response), then contract-verify against a disposable repository per the
   standard playbook.

## What NOT to do

- Do not implement against the docs-page description.
- Do not probe `local-dev-access` further with the current token — the
  empty-grants result is already recorded; repeat probes add no evidence.

## Acceptance criteria

- This ticket closes when either unblock path yields a captured contract,
  at which point a normal implementation ticket is cut (plan-first command,
  likely `pltr orchestration transform-preview` per the registry's mapped
  command name, tests, docs, CHANGELOG), or when Palantir publishes the
  endpoint in a stable API and the SDK picks it up.
