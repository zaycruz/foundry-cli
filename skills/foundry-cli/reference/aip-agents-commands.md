# AIP Agents Commands

Commands for managing AIP Agents, their conversation sessions, and version history in Foundry.

## RID Formats
- **Agent**: `ri.foundry.main.agent.{uuid}`
- **Session**: `ri.foundry.main.session.{uuid}`

## Agent Commands

### Get Agent

Get detailed information about an AIP Agent.

```bash
foundry aip-agents get AGENT_RID [OPTIONS]

# Options:
#   --version, -v TEXT      Agent version (e.g., '1.0') [default: latest published]
#   --format, -f TEXT       Output format (table, json, csv)
#   --output, -o TEXT       Output file path
#   --profile, -p TEXT      Profile name

# Examples

# Get latest published version of agent
foundry aip-agents get ri.foundry.main.agent.abc123

# Get specific version
foundry aip-agents get ri.foundry.main.agent.abc123 --version 1.5

# Output as JSON
foundry aip-agents get ri.foundry.main.agent.abc123 --format json

# Save to file
foundry aip-agents get ri.foundry.main.agent.abc123 \
    --format json \
    --output agent-info.json
```

## Session Commands

### List Sessions

List conversation sessions for an agent.

**Important:** This only lists sessions created via the API. Sessions created in AIP Agent Studio will not appear.

```bash
foundry aip-agents sessions list AGENT_RID [OPTIONS]

# Options:
#   --page-size INTEGER     Number of sessions per page
#   --max-pages INTEGER     Maximum pages to fetch [default: 1]
#   --all                   Fetch all available sessions (overrides --max-pages)
#   --format, -f TEXT       Output format (table, json, csv)
#   --output, -o TEXT       Output file path
#   --profile, -p TEXT      Profile name

# Examples

# List first page of sessions
foundry aip-agents sessions list ri.foundry.main.agent.abc123

# List all sessions
foundry aip-agents sessions list ri.foundry.main.agent.abc123 --all

# List first 3 pages with 50 sessions each
foundry aip-agents sessions list ri.foundry.main.agent.abc123 \
    --page-size 50 --max-pages 3

# Export to CSV
foundry aip-agents sessions list ri.foundry.main.agent.abc123 \
    --all --format csv --output sessions.csv
```

### Get Session

Get detailed information about a specific conversation session.

```bash
foundry aip-agents sessions get AGENT_RID SESSION_RID [OPTIONS]

# Options:
#   --format, -f TEXT       Output format (table, json, csv)
#   --output, -o TEXT       Output file path
#   --profile, -p TEXT      Profile name

# Examples

# Get session details
foundry aip-agents sessions get \
    ri.foundry.main.agent.abc123 \
    ri.foundry.main.session.xyz789

# Export session details to JSON
foundry aip-agents sessions get \
    ri.foundry.main.agent.abc123 \
    ri.foundry.main.session.xyz789 \
    --format json --output session.json
```

## Version Commands

### List Versions

List all versions for an AIP Agent. Versions are returned in descending order (most recent first).

```bash
foundry aip-agents versions list AGENT_RID [OPTIONS]

# Options:
#   --page-size INTEGER     Number of versions per page
#   --max-pages INTEGER     Maximum pages to fetch [default: 1]
#   --all                   Fetch all available versions (overrides --max-pages)
#   --format, -f TEXT       Output format (table, json, csv)
#   --output, -o TEXT       Output file path
#   --profile, -p TEXT      Profile name

# Examples

# List first page of versions
foundry aip-agents versions list ri.foundry.main.agent.abc123

# List all versions
foundry aip-agents versions list ri.foundry.main.agent.abc123 --all

# Export all versions to CSV
foundry aip-agents versions list ri.foundry.main.agent.abc123 \
    --all --format csv --output versions.csv
```

## Session Visibility Note

**API Sessions Only:** The `sessions list` command only shows sessions created through the API. Sessions created interactively in AIP Agent Studio are not visible through this endpoint.

To work with all sessions including those from AIP Agent Studio, use the Foundry web interface.

## Pagination

Both `sessions list` and `versions list` support pagination:

| Option | Description |
|--------|-------------|
| `--page-size N` | Number of items per page |
| `--max-pages N` | Maximum pages to fetch (default: 1) |
| `--all` | Fetch all available items |

```bash
# Fetch first 100 sessions across 2 pages of 50 each
foundry aip-agents sessions list ri.foundry.main.agent.abc123 \
    --page-size 50 --max-pages 2

# Fetch everything
foundry aip-agents sessions list ri.foundry.main.agent.abc123 --all
```

## Common Patterns

### Inspect Agent Before Using

```bash
# Get agent details to understand its capabilities
foundry aip-agents get ri.foundry.main.agent.abc123 --format json

# Check available versions
foundry aip-agents versions list ri.foundry.main.agent.abc123
```

### Export Session History

```bash
# List all sessions and export
foundry aip-agents sessions list ri.foundry.main.agent.abc123 \
    --all \
    --format json \
    --output all-sessions.json

# Get details for specific session
foundry aip-agents sessions get \
    ri.foundry.main.agent.abc123 \
    ri.foundry.main.session.xyz789 \
    --format json \
    --output session-details.json
```

### Track Agent Version History

```bash
# Export complete version history
foundry aip-agents versions list ri.foundry.main.agent.abc123 \
    --all \
    --format csv \
    --output agent-versions.csv
```

### Compare Agent Versions

```bash
# Get specific version details
foundry aip-agents get ri.foundry.main.agent.abc123 --version 1.0 \
    --format json --output v1.json

foundry aip-agents get ri.foundry.main.agent.abc123 --version 2.0 \
    --format json --output v2.json

# Compare with diff
diff v1.json v2.json
```
