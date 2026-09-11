# AI FDE Commands

AI FDE thread and settings operations, backed by the internal `ai-fde`
Conjure service plus pinned GraphQL gateway operations. All contracts were
captured from the live AI FDE UI on a live Foundry deployment via
Chrome DevTools Protocol on 2026-09-04; every listed call returned HTTP 200
(capture artifact: `/tmp/evals-capture/capture.jsonl`).

Thread IDs are plain UUIDs, not RIDs.

Key architectural finding: **the AI FDE agent loop runs client-side** in the
Foundry UI — the browser calls the LLM directly and executes tool calls
itself. The `threads`/`settings` commands manage the thread document and
user settings; `ai-fde run` reimplements that client-side loop in the CLI
(LLM call → tool execution → thread write-back; see
`tickets/TICKET-009-ai-fde.md` for the remaining gaps).

Thread creation is the CLI's one scoped GraphQL mutation exception:
`CreateThreadMutation` is a captured, registry-pinned operation and the
general GraphQL mutation ban stands for everything else.

## Thread Commands

### List Threads

```bash
pfoundry ai-fde threads list [--page-size N] [--format FORMAT]

# GraphQL AvailableThreadsQuery {pageSize} -> aiFdeThreadsV2. Returns the
# raw thread metadata entries (full or redacted).

# Example
pfoundry ai-fde threads list --page-size 50
```

### Get Thread Metadata

```bash
pfoundry ai-fde threads get THREAD_ID [--format FORMAT]

# GraphQL ThreadMetadataQuery {threadId} -> aiFdeThreadV2.metadataV3: id,
# name, version (the threadVersion used for optimistic concurrency),
# agentState, contextItemsOrder. Redacted threads return the reduced
# captured shape.

# Example
pfoundry ai-fde threads get 00000000-0000-0000-0000-000000000001
```

### Get Thread Context Items

```bash
pfoundry ai-fde threads items THREAD_ID [--page-size N] [--page-token TOKEN] [--format FORMAT]

# GraphQL ThreadContextItemsPageQuery {threadId, pageSize, pageToken} ->
# aiFdeThreadV2.contextItemsV2.contextItems. Returns one page of typed
# context items (user-message, assistant-message, tool-usage,
# executedAction, evaluationRun, evaluationSuite, ...) plus nextPageToken.

# Example
pfoundry ai-fde threads items 00000000-0000-0000-0000-000000000001 --page-size 50
```

### Create a Thread (write; scoped GraphQL mutation)

```bash
pfoundry ai-fde threads create --name NAME [--format FORMAT]

# Captured CreateThreadMutation {threadName} with contextItems: []
# hardcoded -> createAiFdeThread {id, version}. Runs through the client's
# scoped mutation exception (VERIFIED_GRAPHQL_MUTATION_NAMES registry +
# per-call opt-in); the general mutation ban stands.

# Example
pfoundry ai-fde threads create --name "New session"
```

### Send a User Message (write)

```bash
pfoundry ai-fde threads send THREAD_ID --message TEXT [--format FORMAT]

# Fetches the current thread metadata, then PUT
# /ai-fde/api/threads/{threadId}/update with body {currentVersion,
# itemIdsInOrder, itemsToWrite} appending one captured-shape user-message
# context item. Prints the resulting threadVersion. The message is queued
# in the thread document; the agent loop itself runs client-side in the
# Foundry UI. The itemsToWrite minimal-delta behavior is contract-verified
# (2026-09-05, second live deployment, HTTP 200 + read-back).

# Example
pfoundry ai-fde threads send 00000000-0000-0000-0000-000000000001 --message "Investigate the failing evals"
```

### Get Thread Agent State

```bash
pfoundry ai-fde threads metadata get THREAD_ID [--format FORMAT]

# The agentState from ThreadMetadataQuery: system prompt, tool
# configurations, mode config, model configuration. Redacted threads carry
# no agent state and fail loudly.
```

### Update Thread Agent State (write)

```bash
pfoundry ai-fde threads metadata update THREAD_ID --current-version VERSION --agent-state FILE [--format FORMAT]

# PUT /ai-fde/api/threads/{threadId}/metadata with body {currentVersion,
# agentStateModification}; FILE is a JSON document ('-' reads stdin) sent
# verbatim. The captured modification is a full agent-state document.
# Response carries the new threadVersion.

# Example
pfoundry ai-fde threads metadata update 00000000-0000-0000-0000-000000000001 \
    --current-version 8041e2bb-45d0-4ec2-bf71-530f77fa8ffa \
    --agent-state agent-state.json
```

## Settings Commands

### Get Settings

```bash
pfoundry ai-fde settings get [--format FORMAT]

# GET /ai-fde/api/settings -> {attributionSettings,
# skillEnablementSettings, bulkToolApprovalSettings,
# modelSelectionSettings}.
```

### Update Settings (write)

```bash
pfoundry ai-fde settings update --definition FILE [--format FORMAT]

# POST /ai-fde/api/settings with a settings modification document sent
# verbatim ('-' reads stdin). The captured shape wraps each section in an
# unchanged/modification union; only the skillEnablementSettings
# modification arm was observed. Success response is {}.

# Example
pfoundry ai-fde settings update --definition settings-modification.json
```

## Agent Loop

### Run the Agent (write; approval-gated)

```bash
pfoundry ai-fde run "INSTRUCTION" [--thread THREAD_ID] [--name NAME]
  [--max-turns N] [--yes] [--all-tools] [--tools CSV] [--model MODEL]
  [--format FORMAT]

# Reimplements the Foundry UI's client-side agent loop: sends INSTRUCTION
# to a new (or --thread-resumed) thread, calls the LLM (PUT
# /language-model-service/api/llm/v3/completion/{model}/
# streamCompletionChunk, OpenAI-Responses shape, sessionId == threadId),
# executes the returned tool calls against captured internal contracts,
# writes tool-usage and assistant-message items back into the thread, and
# repeats until the model stops calling tools or --max-turns is hit
# (default 25). Progress (turns, tool calls, approvals) streams to stderr.
# Default stdout is the final assistant text rendered as Markdown; use
# -f json for the structured run report {threadId, status, turns,
# toolsCalled, toolCalls, finalText, usage, model}.
#
# IDENTIFYING RESOURCES: the captured AI FDE catalog has NO
# resource-search tool — not even the full 72 (the UI identifies
# resources via user @-mentions, which this loop cannot do). The CLI
# therefore adds pfoundry_* extension tools (below) so the agent can
# resolve names to RIDs itself; naming RIDs explicitly in the
# instruction is still the most reliable path.
#
# CLI EXTENSION TOOLS (pfoundry-native, NOT captured AI FDE tools —
# marked cliExtension in the registry and advertised as CLI-provided in
# the instructions): always exposed, never mode-gated, all read-risk.
# - pfoundry_search_resources {query, limit?} — title search -> RID
#   (wraps the same SearchService as `pfoundry search`). NOTE: ontology
#   object types are NOT Compass resources; use the next tool for them.
# - pfoundry_search_object_types {query, ontologyRid?, limit?} — find
#   object types by case-insensitive substring of api_name/display_name
#   (wraps OntologyService.list_ontologies +
#   ObjectTypeService.list_object_types); without ontologyRid every
#   visible ontology is searched and hits are tagged with it.
# - pfoundry_search_builds {datasetRid?, branch?, createdAfter?, limit?}
#   — recent builds newest-first (wraps OrchestrationService around SDK
#   Build.search/Build.jobs); datasetRid filtering is client-side over
#   job outputs (the SDK filter vocabulary has no dataset member) and
#   the result reports how many builds were scanned.
# - pfoundry_get_dataset_transactions {datasetRid, branch?, limit?} —
#   dataset transaction history (wraps DatasetService.get_transactions /
#   get_branch_transactions).
# - pfoundry_get_resource {rid} — Compass resource metadata (wraps
#   ResourceService.get_resource).
# Extension calls flow through the same write-back/report machinery as
# captured tools, and executor errors come back as tool output (the loop
# never crashes on a failing extension call).
#
# Tool exposure: the full captured 72-tool catalog is registered verbatim.
# By default the model sees the captured 8-tool base set (no mode
# selected); change_mode swaps the offered set per the mined mode mapping
# (functionsEditing -> 51 tools; the executeAction capability adds
# execute_action + await_automation_execution; other modes were never
# captured and keep the current set). --all-tools exposes all 72 from
# turn 1; --tools restricts to a CSV subset.
#
# Live executors (25): ontology_sql_query, evals reads
# (list_evaluation_runs, load_evaluation_runs, get_test_case_results,
# get_evaluation_suite_definition, get_evaluation_suites_for_target),
# run_evaluation_suite, execute_action (validate-then-apply),
# load_object_types, load_action_types, load_link_types,
# get_action_types_for_object_type, get_link_types_for_object_type,
# load_object_sets, load_functions, load_code_repo, load_pull_request,
# container_git_status, container_execute_terminal_command, load_skill,
# and the state tools (change_mode, enable_capabilities,
# disable_capabilities, manage_context, request_clarification_from_user).
# The other 47 fail closed with a typed UnverifiedContract tool result
# (evidence: services/ai_fde_loop.py docstring): the schedules family and
# ci_checks (never exercised; no endpoint captured), the logic family,
# documentation tools, container file writes, and more. Fail-closed write
# tools never prompt for approval.
#
# Approval gate: live write tools (execute_action, run_evaluation_suite,
# container_execute_terminal_command) never run silently. Interactive
# runs prompt per write tool; --yes approves all; --agent /
# non-interactive runs without --yes decline writes while read tools
# still execute.
#
# Clarification loop guard: after 2 consecutive
# request_clarification_from_user calls with no other tool use between,
# the loop injects a directive telling the agent to make reasonable
# assumptions and answer best-effort (with a remaining-turns countdown).
# Interactive prompting still happens when stdin is a TTY.

# Examples
pfoundry ai-fde run "Why did the latest evaluation run fail?" --yes
pfoundry ai-fde run "Check CI for repo ri.stemma.main.repository.00000000-0000-0000-0000-000000000001" --all-tools
pfoundry ai-fde run "Summarize run history" --tools list_evaluation_runs
pfoundry ai-fde run "Follow up on the fix" --thread 00000000-0000-0000-0000-000000000001
```
