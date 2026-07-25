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

Backed by the internal webhooks API (`/registry/v0`). The create contract is
contract-verified up to the Compass permission boundary (2026-07-24, a live Foundry deployment);
the 2xx success shape is UNVERIFIED and passed through raw.

### Get Webhook (read-only)

```bash
pltr connectivity webhook get WEBHOOK_RID [--version N] [--format FORMAT]

# Example
pltr connectivity webhook get ri.magritte..source.abc123
```

### Create Webhook (plan-first)

```bash
pltr connectivity webhook create NAME \
    --source-rid SOURCE_RID [--api-name NAME] [--description TEXT] \
    [--spec JSON | --spec-file FILE] [--apply] [--format FORMAT]

# Without --apply: prints the dry-run plan (the exact request body) and
# issues no network request. --apply sends the verified body; a permission
# failure surfaces as a loud error.

# Example
pltr connectivity webhook create my-webhook \
    --source-rid ri.magritte..source.abc123 --spec-file webhook-spec.json --apply
```

### Update Webhook (plan-first; --apply currently blocked)

```bash
pltr connectivity webhook update WEBHOOK_RID SPEC_JSON [--spec-file FILE] [--apply]

# Publishes a new webhook version. Only the `spec` request key is verified;
# the full body could not be recovered (creation is permission-blocked on
# a live Foundry deployment), so --apply refuses rather than guessing. Without --apply
# the command prints the dry-run plan and issues no network request.

# Example
pltr connectivity webhook update ri.magritte..source.abc123 '{"url": "https://api.example.com/hook"}'
```

## REST Source Commands

### Create REST API Source (plan-only; --apply currently blocked)

```bash
pltr connectivity rest-source create NAME \
    --host HOST [--scheme https] [--port 443] [--apply] [--format FORMAT]

# Backed by magritte-coordinator POST /source-store/source/v2 (or /v3).
# The write contract could NOT be recovered -- the service drops unknown
# JSON keys leniently and every candidate envelope was rejected with
# 400 Default:InvalidArgument (2026-07-24, a live Foundry deployment). The command is
# plan-only: the printed candidate body models the live REDACTED config
# shape with dummy values, is labeled as server-rejected, and is never
# sent. --apply refuses rather than guessing. The CLI never calls the
# plaintext-secret config endpoint and never accepts real credentials.

# Example
pltr connectivity rest-source create my-rest-source --host api.example.com
```

## Data-Source Webhook Commands

Backed by the internal webhooks registry API. Write commands are plan-first:
they print a dry-run plan by default and issue no network request.

### Get Webhook (read-only)

```bash
pltr connectivity webhook get WEBHOOK_RID [--version N] [--format FORMAT]

# Example
pltr connectivity webhook get ri.webhooks.main.webhook.abc123
```

### Create Webhook (plan-first)

`create --apply` sends the contract-verified request body
(`{name, apiName, description, spec, executionPolicy}`, verified
up to the Compass permission boundary on a live Foundry deployment). The 2xx success
shape is UNVERIFIED and passed through raw. The API name must match a
server-enforced pattern (a letters-only PascalCase name is accepted;
trailing digits were rejected in validation).

```bash
pltr connectivity webhook create NAME --source-rid SOURCE_RID \
  [--api-name NAME] [--description TEXT] [--spec-file PATH] \
  [--apply] [--format FORMAT]

# Dry-run plan (default)
pltr connectivity webhook create my-webhook \
  --source-rid ri.magritte..source.abc123

# Real create (fails loudly on 403 Compass:InsufficientPermissions)
pltr connectivity webhook create my-webhook \
  --source-rid ri.magritte..source.abc123 --api-name MyWebhook --apply
```

### Update Webhook (plan-first; --apply blocked)

Publishes a new webhook version. The publish contract is UNVERIFIED
(2026-07-24 validation confirmed only the `spec` request key), so `--apply`
refuses with an `unverified-write-contract` error instead of guessing.

```bash
pltr connectivity webhook update WEBHOOK_RID SPEC_JSON [--apply] [--format FORMAT]

# Dry-run plan (default)
pltr connectivity webhook update ri.webhooks.main.webhook.abc123 '{"inputs": []}'
```

## REST API Data Source Commands

### Create REST API Data Source (plan-only; --apply blocked)

The magritte-coordinator `addSourceV2/V3` write contract could NOT be
recovered (2026-07-24: the service drops unknown keys leniently, defeating
field validation, and every candidate envelope was rejected). The command
ships plan-only; the printed candidate body models the live REDACTED config
shape with dummy values and is never sent. This CLI never calls the
plaintext-secret config endpoint and never accepts real credentials.

```bash
pltr connectivity rest-source create NAME --host HOST \
  [--scheme HTTPS] [--port 443] [--apply] [--format FORMAT]

# Dry-run plan (default, and the only mode)
pltr connectivity rest-source create my-source --host example.invalid
```
