# Dataset Commands

## Dataset RID Format
`ri.foundry.main.dataset.{uuid}`

## Get Dataset Info

```bash
pfoundry dataset get DATASET_RID [--profile PROFILE] [--format FORMAT] [--output FILE]

# Example
pfoundry dataset get ri.foundry.main.dataset.abc123
pfoundry dataset get ri.foundry.main.dataset.abc123 --format json --output info.json
```

## Dataset Statistics

```bash
pfoundry dataset stats DATASET_RID [--branch BRANCH] \
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
pfoundry dataset create NAME [--parent-folder FOLDER_RID] [--profile PROFILE]

# Example
pfoundry dataset create "My New Dataset"
pfoundry dataset create "Analysis Results" --parent-folder ri.compass.main.folder.xyz789
```

## Branch Operations

```bash
# List branches
pfoundry dataset branches list DATASET_RID

# Create branch
pfoundry dataset branches create DATASET_RID BRANCH_NAME [--parent PARENT_BRANCH]

# Get a single branch
pfoundry dataset branches get DATASET_RID BRANCH_NAME

# Transaction history for one branch
pfoundry dataset branches transactions DATASET_RID BRANCH_NAME

# Delete a branch
pfoundry dataset branches delete DATASET_RID BRANCH_NAME

# Examples
pfoundry dataset branches list ri.foundry.main.dataset.abc123
pfoundry dataset branches create ri.foundry.main.dataset.abc123 "feature-branch"
pfoundry dataset branches create ri.foundry.main.dataset.abc123 "hotfix" --parent development
pfoundry dataset branches get ri.foundry.main.dataset.abc123 master
pfoundry dataset branches transactions ri.foundry.main.dataset.abc123 master
pfoundry dataset branches delete ri.foundry.main.dataset.abc123 "feature-branch"
```

## File Operations

```bash
# List files in dataset
pfoundry dataset files list DATASET_RID [--branch BRANCH]

# Download file from dataset
pfoundry dataset files get DATASET_RID FILE_PATH OUTPUT_PATH [--branch BRANCH]

# Upload a local file (writes inside an open transaction)
pfoundry dataset files upload LOCAL_FILE_PATH DATASET_RID [--branch BRANCH]

# File metadata (size, timestamps, transaction) without downloading
pfoundry dataset files info DATASET_RID FILE_PATH [--branch BRANCH]

# Delete a file from a dataset
pfoundry dataset files delete DATASET_RID FILE_PATH [--branch BRANCH]

# Examples
pfoundry dataset files list ri.foundry.main.dataset.abc123
pfoundry dataset files list ri.foundry.main.dataset.abc123 --branch development

pfoundry dataset files get ri.foundry.main.dataset.abc123 "/data/results.csv" "./results.csv"
pfoundry dataset files get ri.foundry.main.dataset.abc123 "/report.pdf" "./report.pdf" --branch feature

pfoundry dataset files upload "./results.csv" ri.foundry.main.dataset.abc123
pfoundry dataset files info ri.foundry.main.dataset.abc123 "/data/results.csv"
pfoundry dataset files delete ri.foundry.main.dataset.abc123 "/data/stale.csv"
```

## Schema Operations

**Note:** `schema get` requires API preview access. If you example `ApiFeaturePreviewUsageOnly` errors, use `schema apply` instead.

```bash
# Get dataset schema (requires preview access)
pfoundry dataset schema get DATASET_RID [--branch BRANCH]

# Apply/infer schema (works for all users)
pfoundry dataset schema apply DATASET_RID

# Set or replace the schema explicitly (choose one source)
pfoundry dataset schema set DATASET_RID --from-csv CSV_FILE [--branch BRANCH]
pfoundry dataset schema set DATASET_RID --json SCHEMA_JSON [--branch BRANCH]
pfoundry dataset schema set DATASET_RID --json-file SCHEMA_FILE [--branch BRANCH]

# Example
pfoundry dataset schema get ri.foundry.main.dataset.abc123
pfoundry dataset schema apply ri.foundry.main.dataset.abc123
pfoundry dataset schema set ri.foundry.main.dataset.abc123 --json-file schema.json
```

### Additive schema migration (branch-aware, optimistic concurrency)

```bash
# Dry-run (default): shows the fields that would be added, nothing is written
pfoundry dataset schema update DATASET_RID --branch develop \
    --add-field capacity:INTEGER --add-field revision:INTEGER:false:0

# Apply the additive migration with an expected-version check
pfoundry dataset schema update DATASET_RID --branch develop \
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
pfoundry dataset preview DATASET_RID [--limit N]

# Examples
pfoundry dataset preview ri.foundry.main.dataset.abc123
pfoundry dataset preview ri.foundry.main.dataset.abc123 --limit 50
pfoundry dataset preview ri.foundry.main.dataset.abc123 --format csv --output preview.csv
```

## Transaction Operations

Transactions provide atomic operations with rollback capability.

```bash
# List transactions
pfoundry dataset transactions list DATASET_RID

# Start transaction
pfoundry dataset transactions start DATASET_RID [--branch BRANCH]

# Check transaction status
pfoundry dataset transactions status DATASET_RID TRANSACTION_RID

# Commit transaction
pfoundry dataset transactions commit DATASET_RID TRANSACTION_RID

# Abort transaction
pfoundry dataset transactions abort DATASET_RID TRANSACTION_RID

# Build information for a transaction
pfoundry dataset transactions build DATASET_RID TRANSACTION_RID
```

Transaction listing is dataset-wide because the pinned SDK transaction endpoint
does not expose a branch filter.

## Jobs and Schedules

```bash
# Jobs that ran against a dataset
pfoundry dataset jobs list DATASET_RID [--branch BRANCH] [--format FORMAT]

# Schedules that target a dataset
pfoundry dataset schedules list DATASET_RID [--format FORMAT]

# Examples
pfoundry dataset jobs list ri.foundry.main.dataset.abc123
pfoundry dataset schedules list ri.foundry.main.dataset.abc123 --format json
```

## View Operations

```bash
# List views (reports an explicit unsupported-capability warning with SDK 1.95.0)
pfoundry dataset views list DATASET_RID

# Create a view backed by DATASET_RID in the same parent folder
pfoundry dataset views create DATASET_RID VIEW_NAME

# View details
pfoundry dataset views get VIEW_RID [--branch BRANCH] [--format FORMAT]

# Manage backing datasets (comma-separated RIDs)
pfoundry dataset views add-datasets VIEW_RID DATASET_RID,DATASET_RID2
pfoundry dataset views remove-datasets VIEW_RID DATASET_RID,DATASET_RID2
pfoundry dataset views replace-datasets VIEW_RID DATASET_RID,DATASET_RID2

# Add a primary key (comma-separated fields)
pfoundry dataset views add-primary-key VIEW_RID KEY_FIELD,KEY_FIELD2

# Examples
pfoundry dataset views create ri.foundry.main.dataset.abc123 "analysis-view"
pfoundry dataset views get ri.foundry.main.view.abc123
pfoundry dataset views add-datasets ri.foundry.main.view.abc123 ri.foundry.main.dataset.def456
pfoundry dataset views add-primary-key ri.foundry.main.view.abc123 employee_id
```

`foundry-platform-sdk` 1.95.0 exposes `View.create` but not `View.list`, and
`View.create` has no description parameter. The CLI therefore fails closed when
`--description` is supplied instead of silently discarding it.

## Copy Datasets

```bash
# Copy dataset to another folder
pfoundry cp SOURCE_RID TARGET_FOLDER_RID [OPTIONS]

# Options:
#   --branch, -b TEXT     Dataset branch [default: master]
#   --recursive, -r       Required for folders
#   --name-suffix TEXT    Suffix for cloned names [default: -copy]
#   --schema/--no-schema  Copy schemas [default: true]
#   --dry-run             Preview without writing
#   --fail-fast           Stop on first error

# Examples
pfoundry cp ri.foundry.main.dataset.abc123 ri.compass.main.folder.dest456
pfoundry cp ri.compass.main.folder.source789 ri.compass.main.folder.dest456 --recursive
pfoundry cp ri.foundry.main.dataset.abc123 ri.compass.main.folder.dest456 --dry-run
```

## Common Patterns

### Download all files from a dataset
```bash
# List files, then download each
for file in $(foundry dataset files list ri.foundry.main.dataset.abc123 --format json | jq -r '.[].path'); do
  pfoundry dataset files get ri.foundry.main.dataset.abc123 "$file" "./${file##*/}"
done
```

### Export dataset info to JSON
```bash
pfoundry dataset get ri.foundry.main.dataset.abc123 --format json --output dataset-info.json
```
