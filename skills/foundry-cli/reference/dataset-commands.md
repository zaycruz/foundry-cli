# Dataset Commands

## Dataset RID Format
`ri.foundry.main.dataset.{uuid}`

## Get Dataset Info

```bash
foundry dataset get DATASET_RID [--profile PROFILE] [--format FORMAT] [--output FILE]

# Example
foundry dataset get ri.foundry.main.dataset.abc123
foundry dataset get ri.foundry.main.dataset.abc123 --format json --output info.json
```

## Dataset Statistics

```bash
foundry dataset stats DATASET_RID [--branch BRANCH] \
  [--page-size N] [--page-token TOKEN] [--max-pages N] [--fetch-all] \
  [--format agent]
```

Statistics are derived from the verified dataset file and transaction APIs.
The response includes file count, hidden-file count, byte totals, transaction
identifiers, warnings, and pagination coverage. File statistics are scoped to
`--branch`; the SDK transaction endpoint has no branch filter, so transaction
statistics are explicitly marked dataset-wide and the overall result is
partial. Without `--fetch-all`, a continuation token also means file totals
are incomplete.

## Create Dataset

```bash
foundry dataset create NAME [--parent-folder FOLDER_RID] [--profile PROFILE]

# Example
foundry dataset create "My New Dataset"
foundry dataset create "Analysis Results" --parent-folder ri.compass.main.folder.xyz789
```

## Branch Operations

```bash
# List branches
foundry dataset branches list DATASET_RID

# Create branch
foundry dataset branches create DATASET_RID BRANCH_NAME [--parent PARENT_BRANCH]

# Get a single branch
foundry dataset branches get DATASET_RID BRANCH_NAME

# Transaction history for one branch
foundry dataset branches transactions DATASET_RID BRANCH_NAME

# Delete a branch
foundry dataset branches delete DATASET_RID BRANCH_NAME

# Examples
foundry dataset branches list ri.foundry.main.dataset.abc123
foundry dataset branches create ri.foundry.main.dataset.abc123 "feature-branch"
foundry dataset branches create ri.foundry.main.dataset.abc123 "hotfix" --parent development
foundry dataset branches get ri.foundry.main.dataset.abc123 master
foundry dataset branches transactions ri.foundry.main.dataset.abc123 master
foundry dataset branches delete ri.foundry.main.dataset.abc123 "feature-branch"
```

## File Operations

```bash
# List files in dataset
foundry dataset files list DATASET_RID [--branch BRANCH]

# Download file from dataset
foundry dataset files get DATASET_RID FILE_PATH OUTPUT_PATH [--branch BRANCH]

# Upload a local file (writes inside an open transaction)
foundry dataset files upload LOCAL_FILE_PATH DATASET_RID [--branch BRANCH]

# File metadata (size, timestamps, transaction) without downloading
foundry dataset files info DATASET_RID FILE_PATH [--branch BRANCH]

# Delete a file from a dataset
foundry dataset files delete DATASET_RID FILE_PATH [--branch BRANCH]

# Examples
foundry dataset files list ri.foundry.main.dataset.abc123
foundry dataset files list ri.foundry.main.dataset.abc123 --branch development

foundry dataset files get ri.foundry.main.dataset.abc123 "/data/results.csv" "./results.csv"
foundry dataset files get ri.foundry.main.dataset.abc123 "/report.pdf" "./report.pdf" --branch feature

foundry dataset files upload "./results.csv" ri.foundry.main.dataset.abc123
foundry dataset files info ri.foundry.main.dataset.abc123 "/data/results.csv"
foundry dataset files delete ri.foundry.main.dataset.abc123 "/data/stale.csv"
```

## Schema Operations

**Note:** `schema get` requires API preview access. If you example `ApiFeaturePreviewUsageOnly` errors, use `schema apply` instead.

```bash
# Get dataset schema (requires preview access)
foundry dataset schema get DATASET_RID [--branch BRANCH]

# Apply/infer schema (works for all users)
foundry dataset schema apply DATASET_RID

# Set or replace the schema explicitly (choose one source)
foundry dataset schema set DATASET_RID --from-csv CSV_FILE [--branch BRANCH]
foundry dataset schema set DATASET_RID --json SCHEMA_JSON [--branch BRANCH]
foundry dataset schema set DATASET_RID --json-file SCHEMA_FILE [--branch BRANCH]

# Example
foundry dataset schema get ri.foundry.main.dataset.abc123
foundry dataset schema apply ri.foundry.main.dataset.abc123
foundry dataset schema set ri.foundry.main.dataset.abc123 --json-file schema.json
```

### Additive schema migration (branch-aware, optimistic concurrency)

```bash
# Dry-run (default): shows the fields that would be added, nothing is written
foundry dataset schema update DATASET_RID --branch develop \
    --add-field capacity:INTEGER --add-field revision:INTEGER:false:0

# Apply the additive migration with an expected-version check
foundry dataset schema update DATASET_RID --branch develop \
    --expected-schema-version 00000004-0000-0000-0000-000000000000 \
    --fields-json '[{"name":"capacity","type":"INTEGER","nullable":true}]' \
    --apply

# --add-field format: name:TYPE[:nullable[:default]]
# Additive only: type changes on existing fields are rejected.
# --expected-schema-version fails with Datasets:SchemaVersionConflict when the
# current schema version differs (client-side optimistic concurrency).
# After --apply the schema is read back and returned with its new version.
```

## Preview Data

```bash
# Preview dataset contents
foundry dataset preview DATASET_RID [--limit N]

# Examples
foundry dataset preview ri.foundry.main.dataset.abc123
foundry dataset preview ri.foundry.main.dataset.abc123 --limit 50
foundry dataset preview ri.foundry.main.dataset.abc123 --format csv --output preview.csv
```

## Transaction Operations

Transactions provide atomic operations with rollback capability.

```bash
# List transactions
foundry dataset transactions list DATASET_RID

# Start transaction
foundry dataset transactions start DATASET_RID [--branch BRANCH]

# Check transaction status
foundry dataset transactions status DATASET_RID TRANSACTION_RID

# Commit transaction
foundry dataset transactions commit DATASET_RID TRANSACTION_RID

# Abort transaction
foundry dataset transactions abort DATASET_RID TRANSACTION_RID

# Build information for a transaction
foundry dataset transactions build DATASET_RID TRANSACTION_RID
```

Transaction listing is dataset-wide because the pinned SDK transaction endpoint
does not expose a branch filter.

## Jobs and Schedules

```bash
# Jobs that ran against a dataset
foundry dataset jobs list DATASET_RID [--branch BRANCH] [--format FORMAT]

# Schedules that target a dataset
foundry dataset schedules list DATASET_RID [--format FORMAT]

# Examples
foundry dataset jobs list ri.foundry.main.dataset.abc123
foundry dataset schedules list ri.foundry.main.dataset.abc123 --format json
```

## View Operations

```bash
# List views (reports an explicit unsupported-capability warning with SDK 1.95.0)
foundry dataset views list DATASET_RID

# Create a view backed by DATASET_RID in the same parent folder
foundry dataset views create DATASET_RID VIEW_NAME

# View details
foundry dataset views get VIEW_RID [--branch BRANCH] [--format FORMAT]

# Manage backing datasets (comma-separated RIDs)
foundry dataset views add-datasets VIEW_RID DATASET_RID,DATASET_RID2
foundry dataset views remove-datasets VIEW_RID DATASET_RID,DATASET_RID2
foundry dataset views replace-datasets VIEW_RID DATASET_RID,DATASET_RID2

# Add a primary key (comma-separated fields)
foundry dataset views add-primary-key VIEW_RID KEY_FIELD,KEY_FIELD2

# Examples
foundry dataset views create ri.foundry.main.dataset.abc123 "analysis-view"
foundry dataset views get ri.foundry.main.view.abc123
foundry dataset views add-datasets ri.foundry.main.view.abc123 ri.foundry.main.dataset.def456
foundry dataset views add-primary-key ri.foundry.main.view.abc123 employee_id
```

`foundry-platform-sdk` 1.95.0 exposes `View.create` but not `View.list`, and
`View.create` has no description parameter. The CLI therefore fails closed when
`--description` is supplied instead of silently discarding it.

## Copy Datasets

```bash
# Copy dataset to another folder
foundry cp SOURCE_RID TARGET_FOLDER_RID [OPTIONS]

# Options:
#   --branch, -b TEXT     Dataset branch [default: master]
#   --recursive, -r       Required for folders
#   --name-suffix TEXT    Suffix for cloned names [default: -copy]
#   --schema/--no-schema  Copy schemas [default: true]
#   --dry-run             Preview without writing
#   --fail-fast           Stop on first error

# Examples
foundry cp ri.foundry.main.dataset.abc123 ri.compass.main.folder.dest456
foundry cp ri.compass.main.folder.source789 ri.compass.main.folder.dest456 --recursive
foundry cp ri.foundry.main.dataset.abc123 ri.compass.main.folder.dest456 --dry-run
```

## Common Patterns

### Download all files from a dataset
```bash
# List files, then download each
for file in $(foundry dataset files list ri.foundry.main.dataset.abc123 --format json | jq -r '.[].path'); do
  foundry dataset files get ri.foundry.main.dataset.abc123 "$file" "./${file##*/}"
done
```

### Export dataset info to JSON
```bash
foundry dataset get ri.foundry.main.dataset.abc123 --format json --output dataset-info.json
```
