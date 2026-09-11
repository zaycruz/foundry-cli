# Functions Commands

Commands for executing Functions queries and inspecting value types in Foundry.

## RID Formats
- **Query**: `ri.functions.main.query.{uuid}`
- **Value Type**: `ri.functions.main.value-type.{uuid}`

## Query Commands

### Search Functions by Name

```bash
pfoundry functions search QUERY [--limit N] [--format FORMAT]

# Uses the verified internal GraphQL title search; function matching is
# applied locally to the returned page (see the JSON output `local_filters`
# block). Results are capped at --limit and the gateway does not report
# whether more matches exist.

# Examples
pfoundry functions search revenue
pfoundry functions search revenue --limit 50 --format json
```

### Get Query by API Name

Retrieve query metadata by its API name.

```bash
pfoundry functions query get QUERY_API_NAME [OPTIONS]

# Options:
#   --version, -v TEXT      Query version (e.g., '1.0.0') [default: latest]
#   --preview               Enable preview mode
#   --format, -f TEXT       Output format (table, json, csv)
#   --output, -o TEXT       Output file path
#   --profile, -p TEXT      Profile name

# Examples

# Get latest version of query
pfoundry functions query get myQuery

# Get specific version
pfoundry functions query get myQuery --version 1.0.0

# Output as JSON
pfoundry functions query get myQuery --format json

# Save to file
pfoundry functions query get myQuery --format json --output query-info.json
```

### Get Query by RID

Retrieve query metadata by its Resource Identifier.

```bash
pfoundry functions query get-by-rid QUERY_RID [OPTIONS]

# Options:
#   --version, -v TEXT      Query version (e.g., '1.0.0') [default: latest]
#   --preview               Enable preview mode
#   --format, -f TEXT       Output format (table, json, csv)
#   --output, -o TEXT       Output file path
#   --profile, -p TEXT      Profile name

# Examples

# Get query by RID
pfoundry functions query get-by-rid ri.functions.main.query.abc123

# Get specific version
pfoundry functions query get-by-rid ri.functions.main.query.abc123 --version 1.0.0

# Output as JSON
pfoundry functions query get-by-rid ri.functions.main.query.abc123 --format json
```

### Execute Query by API Name

Execute a query by its API name with parameters.

```bash
pfoundry functions query execute QUERY_API_NAME [OPTIONS]

# Options:
#   --parameters, -params TEXT  Query parameters as JSON or @file.json
#   --version, -v TEXT          Query version (e.g., '1.0.0') [default: latest]
#   --preview                   Enable preview mode
#   --format, -f TEXT           Output format (table, json, csv)
#   --output, -o TEXT           Output file path
#   --profile, -p TEXT          Profile name

# Examples

# Execute with inline parameters
pfoundry functions query execute myQuery --parameters '{"limit": 10}'

# Execute with parameters from file
pfoundry functions query execute myQuery --parameters @params.json

# Execute with complex parameters
pfoundry functions query execute myQuery --parameters '{
    "limit": 100,
    "filter": "active",
    "config": {"enabled": true}
}'

# Execute specific version
pfoundry functions query execute myQuery --version 1.0.0 --parameters '{}'

# Save results to file
pfoundry functions query execute myQuery \
    --parameters '{"limit": 50}' \
    --output results.json
```

### Execute Query by RID

Execute a query by its Resource Identifier with parameters.

```bash
pfoundry functions query execute-by-rid QUERY_RID [OPTIONS]

# Options:
#   --parameters, -params TEXT  Query parameters as JSON or @file.json
#   --version, -v TEXT          Query version (e.g., '1.0.0') [default: latest]
#   --preview                   Enable preview mode
#   --format, -f TEXT           Output format (table, json, csv)
#   --output, -o TEXT           Output file path
#   --profile, -p TEXT          Profile name

# Examples

# Execute with inline parameters
pfoundry functions query execute-by-rid ri.functions.main.query.abc123 \
    --parameters '{"limit": 10}'

# Execute with parameters from file
pfoundry functions query execute-by-rid ri.functions.main.query.abc123 \
    --parameters @params.json

# Execute specific version
pfoundry functions query execute-by-rid ri.functions.main.query.abc123 \
    --version 1.0.0 \
    --parameters '{}'
```

## Value Type Commands

### Get Value Type

Retrieve value type definition and structure information.

```bash
pfoundry functions value-type get VALUE_TYPE_RID [OPTIONS]

# Options:
#   --preview               Enable preview mode
#   --format, -f TEXT       Output format (table, json, csv)
#   --output, -o TEXT       Output file path
#   --profile, -p TEXT      Profile name

# Examples

# Get value type details
pfoundry functions value-type get ri.functions.main.value-type.xyz

# Output as JSON
pfoundry functions value-type get ri.functions.main.value-type.xyz --format json

# Save to file
pfoundry functions value-type get ri.functions.main.value-type.xyz \
    --format json \
    --output value-type-info.json
```

## Parameter Types

Functions support various parameter types:

### Primitive Types
```json
{
  "stringParam": "hello",
  "intParam": 42,
  "floatParam": 3.14,
  "boolParam": true
}
```

### Array Types
```json
{
  "items": ["a", "b", "c"],
  "numbers": [1, 2, 3]
}
```

### Struct Types
```json
{
  "config": {
    "enabled": true,
    "maxRetries": 3,
    "options": ["fast", "reliable"]
  }
}
```

### Date and Timestamp Types
```json
{
  "startDate": "2024-01-15",
  "timestamp": 1705363200000
}
```

## JSON Input Methods

Parameters can be provided inline or from a file:

```bash
# Inline JSON
--parameters '{"key": "value"}'

# File reference (prefix with @)
--parameters @params.json
```

## API Name vs RID

Functions can be accessed by either:

| Method | Command | When to Use |
|--------|---------|-------------|
| API Name | `execute` / `get` | When you know the query's API name |
| RID | `execute-by-rid` / `get-by-rid` | When you have the Resource Identifier |

API names are human-readable identifiers assigned to queries, while RIDs are unique system identifiers.

## Versioning

Queries can have multiple versions:

```bash
# Execute latest version (default)
pfoundry functions query execute myQuery --parameters '{}'

# Execute specific version
pfoundry functions query execute myQuery --version 1.0.0 --parameters '{}'
pfoundry functions query execute myQuery --version 2.1.0 --parameters '{}'
```

## Common Patterns

### Explore Query Structure Before Execution

```bash
# First, get query metadata to understand parameters
pfoundry functions query get myQuery --format json

# Then execute with appropriate parameters
pfoundry functions query execute myQuery --parameters '{"limit": 10}'
```

### Execute and Process Results

```bash
# Execute query and save results
pfoundry functions query execute myQuery \
    --parameters '{"filter": "active"}' \
    --format json \
    --output results.json

# Process with jq or other tools
cat results.json | jq '.data | length'
```

### Parameterized Query with File Input

```bash
# Create params.json:
# {
#   "startDate": "2024-01-01",
#   "endDate": "2024-01-31",
#   "status": "completed",
#   "limit": 1000
# }

pfoundry functions query execute monthlyReport --parameters @params.json
```
