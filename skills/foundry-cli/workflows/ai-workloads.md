# AI Workloads Workflow

Operating procedures for AI workloads on Foundry: language model access (Anthropic Claude chat, OpenAI embeddings), enrollment checks, Functions query execution, AIP agent inspection, and ML model registry inspection.

## Contract

This workflow guarantees that the agent:

- verifies model enrollment before sending LLM traffic;
- inspects query metadata before executing a Functions query;
- treats AIP agent and model-registry reads as read-only;
- runs enrollment and model-creation mutations only after explicit operator confirmation and a change-impact assessment.

It does not create, modify, or delete AIP agents, agent sessions, or model versions; the CLI exposes no such commands (see Capability Gaps).

## Phase 1: Verify enrollment

List models available to the current enrollment and check the status of the specific model before use:

```bash
# List language models available to the current enrollment
pfoundry language-models list --profile "$PROFILE"

# Check enrollment status for a specific model
pfoundry language-models status ri.language-model-service..language-model.abc123 \
  --profile "$PROFILE"
```

`status` and `enroll` take a model resource identifier (`ri.language-model-service..language-model.<id>`). If a model is not enrolled, enrollment is a mutation: follow Phase 6.

## Phase 2: Send messages to Claude

Single-turn Q&A:

```bash
pfoundry language-models anthropic messages ri.language-models.main.model.abc123 \
  --message "Summarize the key risks in this incident report" \
  --system "You are a concise operations analyst" \
  --temperature 0.2 \
  --max-tokens 1024 \
  --profile "$PROFILE" \
  --output response.json
```

Multi-turn conversation, tool calling, or extended thinking via `messages-advanced`. Roles are `USER` and `ASSISTANT`:

```bash
# conversation.json:
# {
#   "messages": [
#     {"role": "USER", "content": [{"type": "text", "text": "Hi, I need help with Python"}]},
#     {"role": "ASSISTANT", "content": [{"type": "text", "text": "Happy to help. What do you need?"}]},
#     {"role": "USER", "content": [{"type": "text", "text": "How do I read a CSV file?"}]}
#   ],
#   "maxTokens": 500
# }

pfoundry language-models anthropic messages-advanced ri.language-models.main.model.abc123 \
  --request @conversation.json \
  --profile "$PROFILE" \
  --output reply.json
```

The default `--format` for LLM commands is `json`; responses include token usage (`inputTokens`, `outputTokens`, `totalTokens`).

## Phase 3: Generate embeddings

Single text, batch, and file-based input:

```bash
# Single text
pfoundry language-models openai embeddings ri.language-models.main.model.xyz789 \
  --input "Machine learning is fascinating"

# Batch from file (texts.json: ["Text 1", "Text 2", "Text 3"])
pfoundry language-models openai embeddings ri.language-models.main.model.xyz789 \
  --input @texts.json \
  --profile "$PROFILE" \
  --output corpus-embeddings.json

# Embed a query later and compare against the corpus locally
pfoundry language-models openai embeddings ri.language-models.main.model.xyz789 \
  --input "search query" \
  --output query-embedding.json
```

Similarity comparison happens client-side; the CLI returns vectors only.

## Phase 4: Execute Functions queries

Discover, inspect, then execute. Do not execute a query whose parameters you have not inspected:

```bash
# 1. Discover the query by name (title search, local filtering, capped at --limit)
pfoundry functions search revenue --limit 50 --format json

# 2. Inspect metadata to learn parameter names and types
pfoundry functions query get monthlyReport --format json
# or by RID
pfoundry functions query get-by-rid ri.functions.main.query.abc123 --format json

# 3. Execute with typed parameters (inline JSON or @file.json)
pfoundry functions query execute monthlyReport \
  --parameters '{
    "startDate": "2024-01-01",
    "endDate": "2024-01-31",
    "status": "completed",
    "limit": 1000
  }' \
  --profile "$PROFILE" \
  --format json \
  --output results.json

# Pin a specific version when reproducibility matters
pfoundry functions query execute monthlyReport --version 1.0.0 --parameters '{}'
```

Parameter values are typed JSON: primitives, arrays, structs, dates (`"2024-01-15"`), and timestamps (epoch millis). `functions query execute` runs the query; whether it writes data depends on the query definition, which is why Phase 4 starts with `get`.

## Phase 5: Inspect AIP agents

All `aip-agents` commands are read-only:

```bash
AGENT="ri.foundry.main.agent.abc123"

# Agent configuration (latest published version, or pin one)
pfoundry aip-agents get $AGENT --format json
pfoundry aip-agents get $AGENT --version 1.5 --format json

# Version history (descending, most recent first)
pfoundry aip-agents versions list $AGENT --all --format csv --output versions.csv

# Conversation sessions
pfoundry aip-agents sessions list $AGENT --all --format json --output sessions.json
pfoundry aip-agents sessions get $AGENT ri.foundry.main.session.xyz789 --format json
```

Compare two agent versions:

```bash
pfoundry aip-agents get $AGENT --version 1.0 --format json --output v1.json
pfoundry aip-agents get $AGENT --version 2.0 --format json --output v2.json
diff v1.json v2.json
```

`sessions list` only returns sessions created through the API. Sessions created in AIP Agent Studio are not visible; use the Foundry web interface for those.

## Phase 6: Mutations — enroll a model, create a model

Both mutations below lack a dry-run, plan, or confirmation flag in the CLI. Run them only after explicit operator confirmation, and run `workflows/change-impact-assessment.md` against the surrounding resource first when the change affects shared enrollment or a shared registry folder. The `--preview` flag on other commands enables Foundry preview APIs; it is not a dry run.

```bash
# Enroll/enable a language model for the current enrollment (mutation)
pfoundry language-models enroll ri.language-model-service..language-model.abc123 \
  --profile "$PROFILE"

# Verify the mutation took effect
pfoundry language-models status ri.language-model-service..language-model.abc123 \
  --profile "$PROFILE"

# Create an ML model container in the registry (mutation)
pfoundry models model create "fraud-detector" \
  --folder ri.compass.main.folder.abc123 \
  --profile "$PROFILE" \
  --format json \
  --output model-info.json

# Capture the new model RID for later version operations
cat model-info.json | jq -r '.rid'
```

## Phase 7: Inspect the model registry

Read-only inspection of ML models and versions. This is the `models` module (custom ML models), distinct from `language-models` (LLM chat and embeddings):

```bash
MODEL="ri.foundry.main.model.abc123"

# Model metadata
pfoundry models model get $MODEL --format json

# Version history (token pagination)
pfoundry models version list $MODEL --page-size 50 --format json --output versions.json
pfoundry models version list $MODEL --page-size 50 --page-token <token-from-previous-response>

# Specific version details
pfoundry models version get $MODEL v1.0.0 --format json --output v1.json
```

## Capability Gaps

- **No list-all-models**: the SDK cannot list models in the registry. Discover RIDs via the Foundry web UI or the Ontology API, or maintain your own inventory.
- **AIP agents are read-only**: there are no commands to create, update, or delete agents, sessions, or agent versions. Use AIP Agent Studio.
- **API sessions only**: `aip-agents sessions list` excludes AIP Agent Studio sessions.
- **OpenAI chat is not exposed**: `language-models openai` provides `embeddings` only; chat completions are available for Anthropic models only.
- **No dry-run for mutations**: `language-models enroll` and `models model create` execute immediately; neither offers `--apply`, `--yes`, or a plan mode.
- **`--preview` is not a dry run**: it enables Foundry preview APIs.

## Best Practices

1. **Check enrollment first**: run `language-models status` before sending LLM traffic in scripts.
2. **Inspect before execute**: `functions query get` before `functions query execute`.
3. **Pin versions**: use `--version` for reproducible query executions and agent retrievals.
4. **Save artifacts**: use `--output` to keep responses, embeddings, and version exports for audit and diffing.
5. **Use JSON for scripting**: `--format json` and `jq` for downstream processing.
6. **Verify mutations after applying**: re-run `status` or `model get` to confirm the change.
