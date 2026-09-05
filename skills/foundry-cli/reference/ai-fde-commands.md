# AI FDE Commands

AI FDE thread and settings operations, backed by the internal `ai-fde`
Conjure service plus pinned GraphQL gateway operations. All contracts were
captured from the live AI FDE UI on a live Foundry deployment via
Chrome DevTools Protocol on 2026-09-04; every listed call returned HTTP 200
(capture artifact: `/tmp/evals-capture/capture.jsonl`).

Thread IDs are plain UUIDs, not RIDs.

Key architectural finding: **the AI FDE agent loop runs client-side** in the
Foundry UI — the browser calls the LLM directly and executes tool calls
itself. These commands manage the thread document (create threads, append
user messages, set agent state) and user settings; they do NOT drive the
LLM agent loop, which was never captured (see `tickets/TICKET-009-ai-fde.md`
for the remaining gaps).

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
pfoundry ai-fde threads get 00000000-0000-4000-8000-000000000001
```

### Get Thread Context Items

```bash
pfoundry ai-fde threads items THREAD_ID [--page-size N] [--page-token TOKEN] [--format FORMAT]

# GraphQL ThreadContextItemsPageQuery {threadId, pageSize, pageToken} ->
# aiFdeThreadV2.contextItemsV2.contextItems. Returns one page of typed
# context items (user-message, assistant-message, tool-usage,
# executedAction, evaluationRun, evaluationSuite, ...) plus nextPageToken.

# Example
pfoundry ai-fde threads items 00000000-0000-4000-8000-000000000001 --page-size 50
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
# Foundry UI. NOTE: itemsToWrite delta behavior is partially-derived (only
# a full-thread write was captured).

# Example
pfoundry ai-fde threads send 00000000-0000-4000-8000-000000000001 --message "Investigate the failing evals"
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
pfoundry ai-fde threads metadata update 00000000-0000-4000-8000-000000000001 \
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
