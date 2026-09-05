# TICKET-009: AI FDE thread orchestration (agentic coding/ops assistant)

**Status**: UI capture complete; thread primitives implemented
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
  `threadVersion`. PARTIALLY-DERIVED: only a full-thread write was
  captured, so the minimal-delta behavior of `itemsToWrite` is inferred
  from the field names and marked as such in the service docstring.
- `ai-fde threads metadata get|update` — agent state read (from
  `ThreadMetadataQuery`) and verbatim-body write
  (`PUT /ai-fde/api/threads/{threadId}/metadata`).
- `ai-fde settings get|update` — `GET`/`POST /ai-fde/api/settings`; update
  body sent verbatim (only the `skillEnablementSettings` modification arm
  was captured).

## Remaining gaps (deliberately not built — never captured)

- **Client-side agent loop**: LLM orchestration via
  `streamCompletionChunk` plus client-side tool execution. Capture
  guidance: record a full AI FDE session from user message to completed
  answer with the LLM stream and every `actionsV2` call; note the exact
  `instructions`/`input`/`tools` body, the sessionId↔threadId binding, and
  how tool results are written back into the thread (`assistant-message`,
  `tool-usage` items).
- **Stop/cancel mid-run**: no cancel call was observed. Capture guidance:
  start a long-running agent task in the UI, press stop, and record the
  request (if any) plus the thread state written afterward.
- **Reject-change path**: the UI's change rejection was never exercised.
  Capture guidance: let the agent propose an edit, reject it, and record
  the resulting thread items / metadata writes.
- **Thread delete/rename**: never observed. Capture guidance: rename and
  delete a disposable thread in the UI and record verb/path/body for both.

## Acceptance criteria

- Contracts recorded with verbatim queries/paths/bodies (digest linked
  above). DONE.
- Thread primitive commands work against a live deployment; GraphQL
  mutation exception scoped to named verified operations. DONE (command
  layer implemented; live re-verification recommended on next session).
- Agent loop / stop / reject / delete / rename: captured before any
  implementation is attempted. OPEN.

## Out of scope

- Relaxing the GraphQL mutation ban beyond the registry mechanism.
- Reimplementing the client-side agent loop without capture evidence.
