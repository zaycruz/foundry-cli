# TICKET-007: Reverse-engineer evaluation suite orchestration (AIP Evals)

**Status**: UI capture complete (2026-09-04); commands implemented; config-write endpoint still uncaptured
**Priority**: High — user-requested flagship use case (orchestrating and running evaluation suites)
**Found**: 2026-09-03 reverse-engineering session

## Summary

The CLI has no evaluation-suite surface, and no published client contract
exists for one. Running an evaluation suite (create/trigger a run, poll
status, read results) must be recovered from the AIP Evals web app, following
the same evidence playbook as TICKET-004.

## Evidence ruled out (do not re-search)

- `@palantir/mcp` dists **0.442.0, 0.444.0, 0.445.0**: no eval tools. The
  0.445.0 esbuild sourcemap (re-extracted from npm cacache to
  `/tmp/mcp-inspect/package/dist/cli.cjs.map`, 3674 sources) contains zero
  matches for `eval`/`suite` tool sources and no eval API paths in the bundle.
- Installed `foundry-platform-python` SDK: no evals namespace. v2 modules are
  admin, aip_agents, audit, checkpoints, connectivity, core, data_health,
  datasets, filesystem, functions, geo, language_models, media_sets, models,
  ontologies, orchestration, sql_queries, streams, third_party_applications,
  widgets. Nearest neighbors (`aip_agents`, `language_models`, `functions`)
  expose no evaluation runs.
- Public v2 REST API docs: no evaluations endpoints.

## Capture plan (required first step)

A read-only GraphQL introspection probe through `graphql_bulk` was considered
as a shortcut (2026-09-03) but could not run: no configured Foundry profile
exists in this environment. If a live profile is available, trying
introspection first is still worthwhile — a disabled-introspection response
is itself evidence. Otherwise:

Browser devtools network capture on the AIP Evals app of a live deployment:

1. List evaluation suites; open one suite; view its runs and results.
2. Trigger a suite run; poll until completion.
3. Save the HAR. For each call classify transport:
   - `POST /graphql-gateway/api/bulk` → record the verbatim query document,
     operation name, and variables (the existing
     `FoundryInternalClient.graphql_bulk` read path can prototype these).
   - Conjure-style `/api/...` or `<service>/api/...` → record verb, path,
     body shape.
4. Flag the run trigger specifically: if it is a GraphQL **mutation**, the
   client's read-only ban (`src/foundry_cli/services/foundry_internal_client.py:129`)
   must be revisited as an explicit, scoped policy decision (e.g. an allowlist
   of verified mutation names) — do not silently drop the ban. If it is a
   Conjure POST, it follows the standard `conjure()` path.
5. Strict-deserialization probes per repo playbook: bogus-RID body must 400
   (not 403) to prove the body shape is parsed.

## Implementation sketch (after capture)

1. Reads first: `pfoundry evals suite list|get`, `evals run list|get|status`
   via `graphql_bulk` or Conjure reads, pinned in
   `services/dependency_internal_specs.py`-style operation specs.
2. `evals suite run` (or `evals run create`) ships only after contract
   verification on a disposable suite: trigger → poll → read-back results,
   evidence recorded in the service docstring in the
   `services/global_branching.py:1-43` style. Plan-first output by default,
   `--apply` to execute, matching the repo's mutation-command convention.
3. Until then, fail closed in `services/proposal.py`-style
   `UNSUPPORTED_CAPABILITY_REASONS` — no simulated behavior.

## Acceptance criteria

- HAR-derived contracts recorded in the ticket with verbatim
  queries/paths/bodies.
- Read commands work against a live deployment.
- Run command contract-verified end-to-end on a disposable suite, or
  explicitly fail-closed with the reason recorded.

## Out of scope

- Relaxing the GraphQL mutation ban globally (scoped allowlist only, if the
  run trigger proves to be a mutation).

## Resolution notes (2026-09-04)

UI capture via Chrome DevTools Protocol on a live Foundry deployment
(artifact `/tmp/evals-capture/capture.jsonl`, digest
`/tmp/evals-capture/contracts-digest.md`) recovered the internal
`foundry-evals` Conjure service: 13 endpoints, all PUT, all observed with
HTTP 200. The run trigger is a Conjure PUT
(`/foundry-evals/api/evals/execute/v3/{suiteRid}/run`), not a GraphQL
mutation, so the client's read-only GraphQL ban did not need revisiting.

Implemented (see `src/foundry_cli/services/evals.py` docstring for the full
contract record): `evals suite list|get|evaluators|auto-metrics|
suggested-scope` and `evals run list|summary|test-cases|trigger`. The run
trigger is plan-first: default prints the resolved run body plus the
read-only `suggestedExecutionScope`; `--apply` issues the run and prints
`{buildRid, jobRid, executionId}`.

**Remaining gap**: the suite config-write (suite config update) endpoint was
never observed — the UI appears to embed run-scoped config in the `/run`
body. Suite-level config write remains uncaptured and is deliberately not
implemented.
