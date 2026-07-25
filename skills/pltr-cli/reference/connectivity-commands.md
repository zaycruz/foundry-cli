# Connectivity Commands

Manage connections and data imports from external systems.

## Connection Commands

### List Connections

```bash
pltr connectivity connection list [--format FORMAT] [--output FILE]

# Example
pltr connectivity connection list --format json --output connections.json
```

### Get Connection Details

```bash
pltr connectivity connection get CONNECTION_RID [--format FORMAT]

# Example
pltr connectivity connection get ri.conn.main.connection.12345
```

### Create Connection

```bash
pltr connectivity connection create DISPLAY_NAME PARENT_FOLDER_RID [CONFIGURATION] [WORKER] [OPTIONS]

# Options:
#   --config-file TEXT    Path to JSON file with connection configuration
#   --worker-file TEXT    Path to JSON file with worker configuration

# Examples
pltr connectivity connection create "My Database" ri.compass.main.folder.xyz123 \
  '{"type": "jdbc"}' '{"workerType": "default"}'

# Using config files
pltr connectivity connection create "My Database" ri.compass.main.folder.xyz123 \
  --config-file connection-config.json --worker-file worker-config.json
```

### Get Connection Configuration

```bash
pltr connectivity connection get-config CONNECTION_RID [--format FORMAT]

# Example
pltr connectivity connection get-config ri.conn.main.connection.12345 --format json
```

### Update Connection Secrets

```bash
pltr connectivity connection update-secrets CONNECTION_RID --secrets-file FILE

# Secrets must be provided via file for security (avoids shell history exposure)

# Example (secrets.json: {"password": "secret123", "api_key": "abc..."})
pltr connectivity connection update-secrets ri.conn.main.connection.12345 \
  --secrets-file secrets.json
```

### Update Export Settings

```bash
pltr connectivity connection update-export-settings CONNECTION_RID [SETTINGS] [OPTIONS]

# Options:
#   --settings-file TEXT    Path to JSON file with export settings

# Examples
pltr connectivity connection update-export-settings ri.conn.main.connection.12345 \
  '{"enabled": true, "format": "parquet"}'

# Using settings file
pltr connectivity connection update-export-settings ri.conn.main.connection.12345 \
  --settings-file export-settings.json
```

### Upload JDBC Drivers

```bash
pltr connectivity connection upload-jdbc-drivers CONNECTION_RID DRIVER_FILES...

# Upload custom JAR files for JDBC connections

# Example
pltr connectivity connection upload-jdbc-drivers ri.conn.main.connection.12345 \
  driver.jar custom-driver-v2.jar
```

## File Import Commands

### List File Imports

```bash
pltr connectivity import list-file --connection CONNECTION_RID [--format FORMAT]

# Example
pltr connectivity import list-file --connection ri.conn.main.connection.123
```

### Get File Import Details

```bash
pltr connectivity import get-file IMPORT_RID --connection CONNECTION_RID [--format FORMAT]

# Example
pltr connectivity import get-file ri.import.main.file.12345 \
  --connection ri.conn.main.connection.123
```

## Table Import Commands

### List Table Imports

```bash
pltr connectivity import list-table --connection CONNECTION_RID [--format FORMAT]

# Example
pltr connectivity import list-table --connection ri.conn.main.connection.123
```

### Get Table Import Details

```bash
pltr connectivity import get-table IMPORT_RID --connection CONNECTION_RID [--format FORMAT]

# Example
pltr connectivity import get-table ri.import.main.table.12345 \
  --connection ri.conn.main.connection.123
```

### List all imports for a connection

```bash
CONNECTION="ri.conn.main.connection.123"

echo "File imports:"
pltr connectivity import list-file --connection $CONNECTION

echo "Table imports:"
pltr connectivity import list-table --connection $CONNECTION
```


## Network Egress Policy Commands

### Ensure Egress Policy (read-only)

Find an existing network egress policy covering a hostname. Read-only: if no
policy matches, the command exits loudly with a "would create, mutations not
enabled" message instead of creating one.

```bash
pltr connectivity egress ensure HOSTNAME [--format FORMAT]

# Example
pltr connectivity egress ensure api.example.com
```

## REST Data-Source Webhook Commands

Backed by the internal webhooks registry API (`/webhooks/api/registry/v0`).
Create and update are VERIFIED end-to-end via an `@palantir/mcp` 0.408.0
client contract (2026-07-25, a live Foundry deployment; evidence:
`the captured contract`). Write commands are plan-first:
they print the exact request body by default and only mutate with `--apply`.
Permission failures are resource-scoped -- the caller needs edit rights on
the target source (or its parent project); a 403 means the target is not
editable by this token, not that the endpoint is blocked.

### Get Webhook (read-only)

```bash
pltr connectivity webhook get WEBHOOK_RID [--version N] [--format FORMAT]

# Example
pltr connectivity webhook get ri.webhooks.main.webhook.abc123
```

### Create Webhook (plan-first)

`create --apply` sends the verified body
(`{name, apiName, description, spec, executionPolicy}`) and returns
`{"webhookRid": ..., "version": 1}`. The API name must match a
server-enforced pattern (a letters-only PascalCase name is accepted;
trailing digits were rejected in validation).

```bash
pltr connectivity webhook create NAME --source-rid SOURCE_RID \
  [--api-name NAME] [--description TEXT] [--spec JSON | --spec-file PATH] \
  [--apply] [--format FORMAT]

# Dry-run plan (default, no network request)
pltr connectivity webhook create my-webhook \
  --source-rid ri.magritte..source.abc123

# Real create (fails loudly on a resource-scoped 403)
pltr connectivity webhook create my-webhook \
  --source-rid ri.magritte..source.abc123 --api-name MyWebhook --apply
```

### Update Webhook (plan-first)

Publishes a new webhook version: `POST /registry/v0/{webhookRid}` with body
`{"spec": <same spec shape as create>}` and nothing else (metadata is not
changed by publish). Verified response: `{"webhookRid": ..., "version": N}`.

The replacement spec can be supplied verbatim (`SPEC` / `--spec-file`), or
assembled from MCP tool-arg shaped pieces (`--source-rid` + `--domain` +
`--calls` / `--inputs`). Assembly mirrors the captured MCP transform:

- each call gets a fresh client-generated `callId` UUID,
- `httpQueryParams` map values land in `queryParamsV2` with an EXTRA array
  wrap (`{"realm": [[{...}]]}`); `headers` are NOT wrapped,
- the `--domain` host is resolved to a `domainId` via a read-only
  `GET /magritte-coordinator/api/source-store/source/{sourceRid}/config`
  (the full RID must be in the path; the bare-UUID variant 400s).

```bash
pltr connectivity webhook update WEBHOOK_RID [SPEC_JSON] [--spec-file PATH] \
  [--source-rid RID --domain HOST [--calls JSON | --calls-file PATH] \
   [--inputs JSON | --inputs-file PATH]] [--apply] [--format FORMAT]

# Dry-run plan (default, no mutation)
pltr connectivity webhook update ri.webhooks.main.webhook.abc123 '{"inputs": []}'

# Real publish with an assembled spec
pltr connectivity webhook update ri.webhooks.main.webhook.abc123 \
  --source-rid ri.magritte..source.abc123 --domain api.example.com \
  --calls '[{"httpMethod": "GET", "httpPath": ["users", {"input": "userId"}]}]' \
  --inputs '[{"name": "userId", "dataType": {"type": "string"}}]' --apply
```

## REST API Data Source Commands

Backed by magritte-coordinator `POST /source-store/source/v3` (addSourceV3),
VERIFIED end-to-end via an `@palantir/mcp` 0.408.0 client contract
(2026-07-25, a live Foundry deployment; evidence:
`the captured contract`). The command is plan-first:
it prints the exact request body by default and only mutates with `--apply`.

### Create REST API Data Source (plan-first)

`create --apply` sends the verified envelope `{config, description,
runtimePlatformRequest, parentRid}`; `domains[].domainId` is a
client-generated random UUID per call. The 2xx response is a BARE JSON
STRING -- the new source RID, not an object. Prerequisites:
`magritte:write-resource` on `--parent-rid` (your home folder works; shared
projects may 403) and at least one `--egress-policy-rid` covering
`host:port`. Credentials are NOT part of the create envelope -- configure
them post-create in the Data Connection UI. This CLI never calls the
plaintext-secret config endpoint and never accepts real credentials.

```bash
pltr connectivity rest-source create NAME --host HOST \
  --parent-rid FOLDER_RID --egress-policy-rid POLICY_RID \
  [--description TEXT] [--scheme HTTPS] [--port 443] [--apply] [--format FORMAT]

# Dry-run plan (default, no network request)
pltr connectivity rest-source create my-source --host example.invalid \
  --parent-rid ri.compass.main.folder.abc123 \
  --egress-policy-rid ri.resource-policy-manager.global.network-egress-policy.abc123

# Real create (returns the new source RID)
pltr connectivity rest-source create my-source --host example.invalid \
  --parent-rid ri.compass.main.folder.abc123 \
  --egress-policy-rid ri.resource-policy-manager.global.network-egress-policy.abc123 \
  --apply
```
