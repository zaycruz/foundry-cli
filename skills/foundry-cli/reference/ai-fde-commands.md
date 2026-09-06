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
  [--max-turns N] [--yes] [--tools CSV] [--model MODEL] [--format FORMAT]

# Reimplements the Foundry UI's client-side agent loop: sends INSTRUCTION
# to a new (or --thread-resumed) thread, calls the LLM (PUT
# /language-model-service/api/llm/v3/completion/{model}/
# streamCompletionChunk, OpenAI-Responses shape, sessionId == threadId),
# executes the returned tool calls against captured internal contracts,
# writes tool-usage and assistant-message items back into the thread, and
# repeats until the model stops calling tools or --max-turns is hit
# (default 25). Progress (turns, tool calls, approvals) streams to stderr;
# the final run report {threadId, status, turns, toolsCalled, toolCalls,
# finalText, usage, model} goes to stdout.
#
# Approval gate: write tools (execute_action, run_evaluation_suite) never
# run silently. Interactive runs prompt per write tool; --yes approves
# all; --agent / non-interactive runs without --yes decline writes while
# read tools still execute.
#
# Registered tools (specs captured verbatim from the UI): live read tools
# ontology_sql_query, list_evaluation_runs, load_evaluation_runs,
# get_test_case_results, get_evaluation_suite_definition, load_skill;
# live state tools change_mode, enable_capabilities, disable_capabilities,
# manage_context, request_clarification_from_user; live write tools
# execute_action (validate-then-apply, plan-first) and
# run_evaluation_suite; FAIL-CLOSED (spec registered, executor raises a
# typed UnverifiedContract error because no endpoint was ever captured):
# load_documentation, load_documentation_bundles. --tools restricts the
# offered subset, e.g. --tools list_evaluation_runs,load_evaluation_runs.

# Examples
pfoundry ai-fde run "Why did the latest evaluation run fail?" --yes
pfoundry ai-fde run "Summarize run history" --tools list_evaluation_runs
pfoundry ai-fde run "Follow up on the fix" --thread 00000000-0000-0000-0000-000000000001
```
