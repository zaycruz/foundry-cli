---
name: pltr-cli
description: >-
  Use the pltr CLI to work with Palantir Foundry, including mandatory read-only
  dependency and change-impact assessment before modifying ontology resources,
  actions, queries, datasets, or applications. Also covers SQL, orchestration,
  folders, projects, permissions, and administration. Triggers include Foundry,
  pltr, dependency, impact, downstream, upstream, ontology change, action, query,
  dataset, application, build, schedule, and RID.
---

# pltr-cli: Palantir Foundry CLI

This skill helps you use the pltr-cli to interact with Palantir Foundry effectively.

## Compatibility

- **Skill version**: 1.2.0
- **pltr-cli version**: 0.16.0+
- **Python**: 3.10+
- **Dependencies**: foundry-platform-sdk >=1.95.0,<2.0.0

## Overview

pltr-cli is a comprehensive CLI with 100+ commands for:
- **Dataset operations**: Get info, list files, download files, manage branches and transactions
- **SQL queries**: Execute queries, export results, manage async queries
- **Ontology**: List ontologies, object types, objects, execute actions and queries; plan-first ontology authoring (object/link/action type upserts and deletes via modifyOntology)
- **Orchestration**: Manage builds, jobs, and schedules
- **Filesystem**: Folders, spaces/namespaces, projects, imports, resources, bounded graphs, cross-resource search, and notepads
- **Admin**: User, group, role management, and organization audit logs
- **Connectivity**: External connections, data imports, REST sources and webhooks (plan-first writes), network egress checks
- **MediaSets**: Media file management
- **Language Models**: Interact with Anthropic Claude models and OpenAI embeddings; enrollment list/status/enroll
- **Streams**: Create and manage streaming datasets, publish real-time data
- **Functions**: Execute queries, search functions, inspect value types
- **AIP Agents**: Manage AI agents, sessions, and versions
- **Models**: ML model registry for model and version management
- **Repositories**: Pull-request inspection and verified writes, headless repo context, git clone
- **Global branching**: Ontology Global Branch and Global Proposal reads plus plan-first create/close
- **Dev console & OSDK**: Third-party app inspection, OSDK definition reads, SDK install, local React codegen, platform-SDK introspection
- **Docs**: Search and read the real Foundry documentation corpus
- **Data health**: Data health checks and check reports
- **Dependency analysis**: Evidence-backed dependency paths, coverage gaps, provenance, and complete local graph artifacts
- **Agent contract**: Stable `pltr-agent-v1` envelopes with resumable pagination for native discovery and dataset statistics

## Command ground truth

Run `pltr agent-manifest` for authoritative command names, arguments, and flags.
The `reference/*.md` files explain usage and workflows; they are not authoritative.
When a reference document conflicts with the manifest, follow the manifest.

## Critical Concepts

### RID-Based API
The Foundry API is **RID-based** (Resource Identifier). Most commands require RIDs:
- **Datasets**: `ri.foundry.main.dataset.{uuid}`
- **Folders**: `ri.compass.main.folder.{uuid}` (root: `ri.compass.main.folder.0`)
- **Builds**: `ri.orchestration.main.build.{uuid}`
- **Schedules**: `ri.orchestration.main.schedule.{uuid}`
- **Ontologies**: `ri.ontology.main.ontology.{uuid}`

Users must know RIDs in advance (from Foundry web UI or previous API calls).

### Authentication
Before using any command, ensure authentication is configured:
```bash
# Configure interactively
pltr configure configure

# Or use environment variables (CI / automation).
# Used only when no --profile is given and no profile is configured, so an
# exported variable never overrides a stored profile.
export FOUNDRY_TOKEN="your-token"
export FOUNDRY_HOST="foundry.company.com"

# Verify connection
pltr verify
```

### Output Formats
All commands support multiple output formats:
```bash
pltr <command> --format table    # Default: Rich table
pltr <command> --format json     # JSON output
pltr <command> --format csv      # CSV format
pltr <command> --output file.csv # Save to file
```

### Profile Selection
Use `--profile` to switch between Foundry instances:
```bash
pltr <command> --profile production
pltr <command> --profile development
```

## Choosing the right tool

Decide the entry point from the situation, not from the command group name:

| Situation | Start with |
|-----------|------------|
| You have a name or path, not a RID | `pltr search`, `pltr namespace list`, `pltr folder list` |
| You are unsure what the CLI can do | `pltr agent-manifest` (authoritative grammar), `pltr capabilities` |
| You are about to change any Foundry resource | `workflows/change-impact-assessment.md` — always, before planning |
| You need docs on a Foundry feature | `pltr docs search` / `pltr docs page`, before guessing flags |
| You are scripting or feeding another agent | `--agent` envelope or `--format json --output file`; never parse table output |
| A command reports `unsupported-capability` | Stop and document the gap; do not simulate the result another way |
| A mutation has no `--apply`/`--yes` flag | Present the exact command and require explicit operator confirmation |

General rules: reads before writes, narrowest target first (`dependency property` over
`dependency resource`), dry-run/plan before `--apply`, and keep artifacts
(`--graph-output`, `--output`) for anything you may need to diff later.

## Reference Files

Load these files based on the user's task:

| Task Type | Reference File |
|-----------|----------------|
| Setup, authentication, getting started | `reference/quick-start.md` |
| CLI introspection (agent-manifest, capabilities), aliases | `reference/cli-utility-commands.md` |
| Dataset operations (get, files, branches, transactions, views, jobs, schedules) | `reference/dataset-commands.md` |
| SQL queries | `reference/sql-commands.md` |
| Builds, jobs, schedules | `reference/orchestration-commands.md` |
| Ontologies, objects, actions, plan-first ontology authoring | `reference/ontology-commands.md` |
| Users, groups, roles, orgs, audit logs | `reference/admin-commands.md` |
| Folders, spaces/namespaces, projects, imports, resources, permissions, graphs, search, notepads | `reference/filesystem-commands.md` |
| Connections, imports, REST sources/webhooks, egress | `reference/connectivity-commands.md` |
| Media sets, media items | `reference/mediasets-commands.md` |
| Anthropic Claude models, OpenAI embeddings, enrollment | `reference/language-models-commands.md` |
| Streaming datasets, real-time data publishing | `reference/streams-commands.md` |
| Functions queries, function search, value types | `reference/functions-commands.md` |
| AIP Agents, sessions, versions | `reference/aip-agents-commands.md` |
| ML model registry, model versions | `reference/models-commands.md` |
| Repository pull requests, repo context, clone | `reference/repository-commands.md` |
| Ontology Global Branches and Global Proposals | `reference/global-branching-commands.md` |
| Dev console, OSDK, platform-SDK introspection, third-party apps | `reference/dev-console-commands.md` |
| Foundry documentation corpus | `reference/docs-commands.md` |
| Data health checks and reports | `reference/data-health-commands.md` |
| Proposal review workflows | `reference/proposal-commands.md` |
| Custom widget sets and releases | `reference/widgets-commands.md` |
| Dependency and change-impact analysis | `reference/dependency-commands.md` |
| Compute Modules (info, logs, plan-first manage/execute) | `reference/compute-commands.md` |

## Workflow Files

For common multi-step tasks:

| Workflow | File |
|----------|------|
| Data exploration, SQL analysis, ontology queries | `workflows/data-analysis.md` |
| ETL pipelines, scheduled jobs, data quality | `workflows/data-pipeline.md` |
| Batch/streaming ingestion with transaction rollback | `workflows/data-ingestion.md` |
| Failed or stuck build diagnosis and remediation | `workflows/build-triage.md` |
| Plan-first ontology schema authoring via branches and proposals | `workflows/ontology-authoring.md` |
| Code PR and Ontology Global Proposal review | `workflows/proposal-review.md` |
| OSDK app development end-to-end (SDK gen, React scaffold, widgets) | `workflows/osdk-app-development.md` |
| Compute Module dev mode, logs, and function execution | `workflows/compute-module-ops.md` |
| MediaSet upload/download with transaction lifecycle | `workflows/media-management.md` |
| Setting up permissions, resource roles, access control | `workflows/permission-management.md` |
| Identity lifecycle, access review, audit-log investigation | `workflows/admin-audit.md` |
| AIP agents, language models, Functions queries, model registry | `workflows/ai-workloads.md` |
| Pre-change Foundry dependency and impact gate | `workflows/change-impact-assessment.md` |

## Common Commands Quick Reference

```bash
# Verify setup
pltr verify

# Current user info
pltr admin user current

# Execute SQL query
pltr sql execute "SELECT * FROM my_table LIMIT 10"

# Get dataset info
pltr dataset get ri.foundry.main.dataset.abc123

# Assess an intended change and retain its complete evidence graph
pltr dependency resource ri.foundry.main.dataset.abc123 \
    --change "rename a column" \
    --change-type rename \
    --output-mode agent \
    --graph-output ./change-impact-before.json

# List files in dataset
pltr dataset files list ri.foundry.main.dataset.abc123

# Download file from dataset
pltr dataset files get ri.foundry.main.dataset.abc123 "/path/file.csv" "./local.csv"

# Copy dataset to another folder
pltr cp ri.foundry.main.dataset.abc123 ri.compass.main.folder.target456

# List folder contents
pltr folder list ri.compass.main.folder.0  # root folder

# Search one verified Compass path; text and type filters apply to each returned page
pltr search "sales" --path-prefix "/Finance" --page-size 100 --format json

# Enumerate notepads from an explicit Compass path
pltr notepad list --path-prefix "/Finance" --page-size 100 --format json

# Search builds
pltr orchestration builds search

# Interactive shell mode
pltr shell start

# Search the Foundry docs corpus
pltr docs search "incremental transforms" --limit 5

# List pull requests for a repository
pltr repository pull-request list ri.stemma.main.repository.abc123

# Inspect an application's OSDK definition
pltr dev-console osdk definition ri.foundry.third-party-application.main.application.abc123

# Send message to Claude model
pltr language-models anthropic messages ri.language-models.main.model.xxx \
    --message "Explain this concept"

# Generate embeddings
pltr language-models openai embeddings ri.language-models.main.model.xxx \
    --input "Sample text"

# Create streaming dataset
pltr streams dataset create my-stream \
    --folder ri.compass.main.folder.xxx \
    --schema '{"fieldSchemaList": [{"name": "value", "type": "STRING"}]}'

# Publish record to stream
pltr streams stream publish ri.foundry.main.dataset.xxx \
    --branch master \
    --record '{"value": "hello"}'

# Execute a function query
pltr functions query execute myQuery --parameters '{"limit": 10}'

# Get AIP Agent info
pltr aip-agents get ri.foundry.main.agent.abc123

# List agent sessions
pltr aip-agents sessions list ri.foundry.main.agent.abc123

# Get ML model info
pltr models model get ri.foundry.main.model.abc123

# List model versions
pltr models version list ri.foundry.main.model.abc123
```

## Best Practices

1. **Verify authentication first**: Run `pltr verify` before starting work.
2. **Assess before changing Foundry**: Load `workflows/change-impact-assessment.md`, retain a baseline artifact, and resolve `must_verify_before_merge`.
3. **Preserve uncertainty**: Partial, unsupported, inaccessible, unresolved, and budget-exhausted coverage are not proof of no impact.
4. **Use appropriate output mode**: `agent` for compact reasoning, `ci` for pipeline gating, and `graph` for full programmatic detail.
5. **Use async for large queries**: `pltr sql submit` + `pltr sql wait` for long-running queries.
6. **Use shell mode for exploration**: `pltr shell start` provides tab completion and history.

## Getting Help

```bash
pltr --help                    # All commands
pltr <command> --help          # Command help
pltr <command> <sub> --help    # Subcommand help
```
