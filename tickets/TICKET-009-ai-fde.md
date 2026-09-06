# TICKET-009: AI FDE thread orchestration (agentic coding/ops assistant)

**Status**: Thread primitives AND the client-side agent loop (MVP) implemented and contract-verified (loop captured from the live UI; LLM call + thread delta writes verified against a second deployment); lifecycle and tool-coverage gaps below remain open
**Priority**: High — flagship agentic surface; thread primitives are the foundation for any agent-loop work
**Found**: 2026-09-04 UI capture session (same CDP capture as TICKET-007 resolution)

## Summary

AI FDE is Palantir's agentic coding/ops assistant inside Foundry. The
2026-09-04 CDP capture (artifact `/tmp/evals-capture/capture.jsonl`, digest
`/tmp/evals-capture/contracts-digest.md`,
a live Foundry deployment, all HTTP 200) recovered its thread and
settings contracts.

## Key architectural finding

**The AI FDE agent loop runs client-side.** The browser calls the LLM
directly
(`language-model-service/api/llm/v3/completion/GPT_5_6_SOL/streamCompletionChunk`,
OpenAI-Responses-shaped body with instructions/input/tools,
sessionId == threadId), executes the returned tool calls itself (e.g.
`POST /actions/api/actionsV2`), and writes the results back into the
thread document. There is no server-side "run the agent" endpoint to wrap;
any CLI-side agent runner would have to reimplement that loop (LLM call →
tool execution → thread sync).

## Implemented (2026-09-04)

Thread primitives — see `src/foundry_cli/services/ai_fde.py` docstring for
the full contract record:

- `ai-fde threads list|get|items` — pinned GraphQL reads
  (`AvailableThreadsQuery`, `ThreadMetadataQuery`,
  `ThreadContextItemsPageQuery`).
- `ai-fde threads create` — captured `CreateThreadMutation`. This is a
  GraphQL mutation, so the client's read-only ban
  (`src/foundry_cli/services/foundry_internal_client.py`) was revisited as
  an explicit, scoped policy decision per this repo's playbook: a
  `VERIFIED_GRAPHQL_MUTATION_NAMES` registry plus a per-call
  `allow_mutation_names` opt-in, both required. The general ban stands for
  every other operation.
- `ai-fde threads send` — appends a captured-shape `user-message` context
  item via `PUT /ai-fde/api/threads/{threadId}/update`; prints the new
  `threadVersion`. The minimal-delta `itemsToWrite` behavior was
  partially-derived at capture time and is now contract-verified
  (2026-09-05, second live deployment: HTTP 200, server-assigned
  `contextItemId`, GraphQL read-back matched the sent message).
- `ai-fde threads metadata get|update` — agent state read (from
  `ThreadMetadataQuery`) and verbatim-body write
  (`PUT /ai-fde/api/threads/{threadId}/metadata`).
- `ai-fde settings get|update` — `GET`/`POST /ai-fde/api/settings`; update
  body sent verbatim (only the `skillEnablementSettings` modification arm
  was captured).

## Implemented (2026-09-04): agent loop MVP

`ai-fde run "<instruction>"` — the CLI-side reimplementation of the
client-side loop (`src/foundry_cli/services/ai_fde_loop.py`, captured tool
specs verbatim in `src/foundry_cli/services/ai_fde_tool_specs.py`). The
loop calls `streamCompletionChunk` itself (JSON-array event format;
attribution `user` == the bearer token itself, live-verified; `sessionId`
== threadId; callIds rewritten to per-call UUIDs per captured UI
behavior), executes tool calls, and writes `tool-usage` /
`assistant-message` items back into the thread. Run report:
`{threadId, status, turns, toolsCalled, toolCalls, finalText, usage}`.

Tool registry (`TOOL_REGISTRY` in the loop module):

- LIVE read tools: `ontology_sql_query` (sql-endpoint SYNC/ARROW,
  pyarrow-decoded into the captured `<ontologySql>` serialization),
  `list_evaluation_runs`, `load_evaluation_runs`, `get_test_case_results`,
  `get_evaluation_suite_definition` (via `EvalsService`), `load_skill`
  (`GET /aip-agents/api/skills/{rid}/latest` after agentState name
  resolution).
- LIVE state tools (client-side only in the capture):
  `change_mode`, `enable_capabilities`, `disable_capabilities`,
  `manage_context` (captured hidden-item serialization),
  `request_clarification_from_user` (interactive prompt; polite
  make-assumptions output in non-interactive runs).
- LIVE write tools, approval-gated and plan-first: `execute_action`
  (`actions/validate` then `actionsV2`; only captured parameter encodings
  — object/object-list with single string primary keys), and
  `run_evaluation_suite` (v2 config parameter/projected-field resolution +
  `LatestFunctionVersionQuery`, then the captured `/run` body; mainBranch
  + projectScoped + function target only).
- FAIL-CLOSED (spec registered verbatim, executor raises typed
  `UnverifiedContract`): `load_documentation`,
  `load_documentation_bundles` — no documentation page-load endpoint
  appears anywhere in the 1896-request capture (only the unrelated
  `/documentation/api/v2/release-notes/pagination`). Also fail-closed at
  the executor level: evals run-history/test-case `pageToken` pagination
  (never captured), non-mainBranch suite target resolution, static
  inputs/experiments, ontology-branch SQL, non-sync SQL results, scalar
  action parameters, composite/non-string primary keys.

Approval gate: write tools never run silently — interactive prompt by
default, `--yes` approves all, `--agent`/non-interactive without `--yes`
declines writes while read tools still execute. Declined writes are
recorded as `tool-usage` items with state `rejected` (DERIVED — a
declined approval was never captured).

Derived (not captured) behaviors, marked as such in the module docstring:
resume input reconstruction (the thread document does not persist tool
result payloads, so prior tool calls are re-presented with an explicit
"result not persisted" note); token counts in `<context-item>` wrappers
are char/4 estimates, not the UI's tokenizer counts; the instructions
block is the captured text minus session-specific lines (run date
substituted; no fabricated user ID or skill catalog) plus an additive
`<cliNotes>` block describing this loop's constraints.

## Remaining gaps (deliberately not built — never captured)
- **Stop/cancel mid-run**: no cancel call was observed. Capture guidance:
  start a long-running agent task in the UI, press stop, and record the
  request (if any) plus the thread state written afterward.
- **Reject-change path**: the UI's change rejection was never exercised.
  Capture guidance: let the agent propose an edit, reject it, and record
  the resulting thread items / metadata writes.
- **Thread delete/rename**: never observed. Capture guidance: rename and
  delete a disposable thread in the UI and record verb/path/body for both.
- **Documentation tool endpoints**: `load_documentation` /
  `load_documentation_bundles` executors fail closed. Capture guidance:
  start a fresh AI FDE session, make the agent load a documentation page
  and a bundle, and record verb/path/body for both.
- **Full mode→tool semantics**: the captured instructions list tool
  CATEGORIES per mode, not tool names, so `change_mode` does not gate the
  offered tool set. Capture guidance: diff the `tools` array of two
  `streamCompletionChunk` requests across a mode switch.
- **Additional fail-closed sub-contracts** (listed in the loop module
  docstring): evals pageTokens, branch arms beyond `mainBranch`,
  staticInputs/experiments, scalar action parameters, ontology-branch SQL.

## Acceptance criteria

- Contracts recorded with verbatim queries/paths/bodies (digest linked
  above). DONE.
- Thread primitive commands work against a live deployment; GraphQL
  mutation exception scoped to named verified operations. DONE (command
  layer implemented; live re-verification recommended on next session).
- Agent loop: captured before implementation. DONE — MVP implemented
  against the capture; live end-to-end run against a real deployment
  recommended on next session.
- Stop / reject / delete / rename / documentation endpoints: captured
  before any implementation is attempted. OPEN.

## Out of scope

- Relaxing the GraphQL mutation ban beyond the registry mechanism.
- Reimplementing the client-side agent loop without capture evidence.
