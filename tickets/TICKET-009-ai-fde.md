# TICKET-009: AI FDE thread orchestration (agentic coding/ops assistant)

**Status**: Thread primitives AND the client-side agent loop implemented and contract-verified (loop captured from the live UI; LLM call + thread delta writes verified against a second deployment); the full 72-tool catalog is registered with a mined mode→tool-set system (25 live executors, 47 fail-closed — matrix below); lifecycle and remaining tool-coverage gaps below stay open
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

## Implemented: full tool catalog + mode system

The complete 72-tool catalog the UI can expose is now registered verbatim
(extracted from the richest captured request, pinned by a SHA-256
regression test), with a mined mode→tool-set system:

- Default (no mode selected): the captured 8-tool base set.
- `change_mode` swaps the exposed set per the capture: `functionsEditing`
  → 51 tools; enabling the `executeAction` capability adds
  `execute_action` AND `await_automation_execution` (53 total). The
  72-tool superset adds the 7 schedule + 12 logic tools; those families
  were enabled client-side mid-session with no capability name recorded
  (modeConfig/sessionState byte-identical across the transition — only
  `toolConfigurations` changed). Other advertised modes were never
  selected, so `change_mode` to them keeps the current set with a note.
- `--all-tools` exposes the full catalog from turn 1.
- The request tool list exactly matches the
  `agentStateModification.toolConfigurations` enabled map the UI writes
  to thread metadata at each transition (the mining key).

### Tool coverage matrix (live vs fail-closed)

LIVE (25): `ontology_sql_query`, `list_evaluation_runs`,
`load_evaluation_runs`, `get_test_case_results`,
`get_evaluation_suite_definition`, `get_evaluation_suites_for_target`,
`run_evaluation_suite`*, `execute_action`*,
`request_clarification_from_user`, `change_mode`, `enable_capabilities`,
`disable_capabilities`, `manage_context`, `load_skill`,
`load_object_types`, `load_action_types`, `load_link_types`,
`get_action_types_for_object_type`, `get_link_types_for_object_type`,
`load_object_sets`, `load_functions`, `load_code_repo`,
`load_pull_request`, `container_git_status`,
`container_execute_terminal_command`* (* = approval-gated write; the
terminal command gates every call because the UI's auto-approval
classifier was not captured; container tools boot a container deployment
as a side effect, exactly as the captured UI does).

FAIL-CLOSED (47 — spec exposed verbatim, executor raises a typed
`UnverifiedContract`; per-tool evidence in the loop module docstring):

- Schedules family (7): `get_dataset_schedules`, `run_schedule`,
  `pause_schedule`, `unpause_schedule`, `create_schedule`,
  `replace_schedule`, `delete_schedule` — **no schedule/orchestration
  endpoint appears anywhere in the 8,143-request capture**, even though
  the 72-tool set exposes the specs.
- `ci_checks` — the tool was never exercised; only UI background polling
  for already-known job/build RIDs was recorded (`GET
  /build2/api/info/jobs3/{jobRid}`, `GET
  /job-tracker/api/builds/{buildRid}`), not the repositoryRid+branch →
  check mapping the tool contract takes.
- Logic family (12): `create_logic_function`,
  `edit_logic_function_definition`, `put_logic_function_definition`,
  `publish_logic_function`, `modify_logic_function_metadata`,
  `get_logic_function_definition`, `get_logic_function_metadata`,
  `get_logic_execution_details`, `list_logic_blocks`,
  `list_logic_executions`, `lookup_logic_block_declarations`,
  `preview_run_logic_function` — exposed but never exercised.
- `await_automation_execution`, `search_language_model_functions`,
  `get_language_model_function`, `get_ontology_sdk_documentation`,
  `refresh_ontology_sdk`, `get_functions_repository_imports`,
  `edit_functions_repository_imports`, `run_functions_diagnostics`,
  `function_preview`, `publish_functions`, `create_branch`,
  `create_code_repo`, `create_or_update_pull_request`,
  `add_missing_project_imports`, `edit_code_workspace_source_imports`,
  `upgrade_code_repository`, `create_evaluation_suite`,
  `edit_evaluation_suite`, `put_evaluation_suite`,
  `get_evaluation_suite_project_scope_readiness` (core
  `suggestedExecutionScope` captured — use `evals suite
  suggested-scope` — but the imports-context half was not),
  `load_documentation`, `load_documentation_bundles`,
  `container_get_file_contents` (endpoint captured, all response bodies
  elided), `container_put_file`, `container_edit_file`,
  `container_sync`, `container_copy_blobster_file_to_repo`.

UX changes shipped with the catalog: default stdout is the final
assistant text as full-width Markdown (`-f json` for the structured
report); run help documents that AI FDE has no resource-search tool even
in the full catalog (name RIDs explicitly — the UI's @-mentions are
unavailable to the CLI); a clarification guard injects a best-effort
directive with a remaining-turns countdown after 2 consecutive
`request_clarification_from_user` calls with no intervening tool use;
the request context budget rises to ~280k estimated tokens (captured
instructions: 1,050,000-token window, 300,000 recommended) so the full
catalog fits without truncating tool outputs.

## Implemented: CLI extension tools (beyond the captured catalog)

Live runs proved the captured 72-tool catalog cannot answer "show me the
most recent runs of the <name> pipeline": the catalog has no name-search
tool (Palantir's design relies on UI @-mentions) and no
build-history/dataset-transaction tool at all. The loop therefore
registers five CLI-native extension tools (`services/
ai_fde_extension_tools.py`; `pfoundry_`-prefixed, `cliExtension: true`,
always exposed, all read-risk) that wrap already-verified pfoundry
surfaces — public SDK / existing service contracts, NOT captured AI FDE
contracts:

- `pfoundry_search_resources` → `SearchService.search` (the pinned
  `SearchTitles` GraphQL query behind `pfoundry search`).
- `pfoundry_search_object_types` → `OntologyService.list_ontologies` +
  `ObjectTypeService.list_object_types` (SDK `Ontology.list` /
  `Ontology.ObjectType.list`). Object types are NOT Compass resources,
  so title search cannot see them; matching is a case-insensitive
  substring of api_name/display_name, all visible ontologies are
  searched when `ontologyRid` is omitted, and per-ontology failures are
  recorded in the result instead of raised.
- `pfoundry_search_builds` → `OrchestrationService.search_builds` /
  `get_build_jobs` (SDK `Build.search` / `Build.jobs`). SDK constraints:
  `where` is required (no-filter searches use `gte STARTED_TIME epoch`)
  and the filter vocabulary has no dataset member, so `datasetRid`
  filtering scans recent builds newest-first and keeps those whose job
  outputs include the dataset RID; the result reports the scan count.
- `pfoundry_get_dataset_transactions` → `DatasetService.get_transactions`
  / `get_branch_transactions` (client-side `limit`).
- `pfoundry_get_resource` → `ResourceService.get_resource`.

## Remaining gaps (deliberately not built — never captured)
- **Stop/cancel mid-run**: no cancel call was observed. Capture guidance:
  start a long-running agent task in the UI, press stop, and record the
  request (if any) plus the thread state written afterward.
- **Reject-change path**: the UI's change rejection was never exercised.
  Capture guidance: let the agent propose an edit, reject it, and record
  the resulting thread items / metadata writes.
- **Thread delete/rename**: never observed. Capture guidance: rename and
  delete a disposable thread in the UI and record verb/path/body for both.
- **Fail-closed tool endpoints** (see the matrix): capture guidance —
  exercise each tool in the UI with the network recorder on. Priority:
  the schedules family (run a schedule from an AI FDE session), CI
  checks (let the agent commit and watch checks), documentation loads,
  and the container file-write family (all currently blocked on elided
  or absent capture evidence).
- **Other-mode tool sets**: capture a `change_mode` to
  `dataIntegration`/`exploration`/etc. and diff the next request's
  `tools` array.
- **Additional fail-closed sub-contracts** (listed in the loop module
  docstring): evals pageTokens, branch arms beyond `mainBranch`,
  staticInputs/experiments, scalar action parameters, ontology-branch
  SQL, associated-action-type pagination.

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
