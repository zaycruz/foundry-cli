# Dataset Commands

## Dataset RID Format
`ri.foundry.main.dataset.{uuid}`

## Get Dataset Info

```bash
pltr dataset get DATASET_RID [--profile PROFILE] [--format FORMAT] [--output FILE]

# Example
pltr dataset get ri.foundry.main.dataset.abc123
pltr dataset get ri.foundry.main.dataset.abc123 --format json --output info.json
```

## Dataset Statistics

```bash
pltr dataset stats DATASET_RID [--branch BRANCH] \
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
pltr dataset create NAME [--parent-folder FOLDER_RID] [--profile PROFILE]

# Example
pltr dataset create "My New Dataset"
pltr dataset create "Analysis Results" --parent-folder ri.compass.main.folder.xyz789
```

## Branch Operations

```bash
# List branches
pltr dataset branches list DATASET_RID

# Create branch
pltr dataset branches create DATASET_RID BRANCH_NAME [--parent PARENT_BRANCH]

# Get a single branch
pltr dataset branches get DATASET_RID BRANCH_NAME

# Transaction history for one branch
pltr dataset branches transactions DATASET_RID BRANCH_NAME

# Delete a branch
pltr dataset branches delete DATASET_RID BRANCH_NAME

# Examples
pltr dataset branches list ri.foundry.main.dataset.abc123
pltr dataset branches create ri.foundry.main.dataset.abc123 "feature-branch"
pltr dataset branches create ri.foundry.main.dataset.abc123 "hotfix" --parent development
pltr dataset branches get ri.foundry.main.dataset.abc123 master
pltr dataset branches transactions ri.foundry.main.dataset.abc123 master
pltr dataset branches delete ri.foundry.main.dataset.abc123 "feature-branch"
```

## File Operations

```bash
# List files in dataset
pltr dataset files list DATASET_RID [--branch BRANCH]

# Download file from dataset
pltr dataset files get DATASET_RID FILE_PATH OUTPUT_PATH [--branch BRANCH]

# Upload a local file (writes inside an open transaction)
pltr dataset files upload LOCAL_FILE_PATH DATASET_RID [--branch BRANCH]

# File metadata (size, timestamps, transaction) without downloading
pltr dataset files info DATASET_RID FILE_PATH [--branch BRANCH]

# Delete a file from a dataset
pltr dataset files delete DATASET_RID FILE_PATH [--branch BRANCH]

# Examples
pltr dataset files list ri.foundry.main.dataset.abc123
pltr dataset files list ri.foundry.main.dataset.abc123 --branch development

pltr dataset files get ri.foundry.main.dataset.abc123 "/data/results.csv" "./results.csv"
pltr dataset files get ri.foundry.main.dataset.abc123 "/report.pdf" "./report.pdf" --branch feature

pltr dataset files upload "./results.csv" ri.foundry.main.dataset.abc123
pltr dataset files info ri.foundry.main.dataset.abc123 "/data/results.csv"
pltr dataset files delete ri.foundry.main.dataset.abc123 "/data/stale.csv"
```

## Schema Operations

**Note:** `schema get` requires API preview access. If you example `ApiFeaturePreviewUsageOnly` errors, use `schema apply` instead.

```bash
# Get dataset schema (requires preview access)
pltr dataset schema get DATASET_RID [--branch BRANCH]

# Apply/infer schema (works for all users)
pltr dataset schema apply DATASET_RID

# Set or replace the schema explicitly (choose one source)
pltr dataset schema set DATASET_RID --from-csv CSV_FILE [--branch BRANCH]
pltr dataset schema set DATASET_RID --json SCHEMA_JSON [--branch BRANCH]
pltr dataset schema set DATASET_RID --json-file SCHEMA_FILE [--branch BRANCH]

# Example
pltr dataset schema get ri.foundry.main.dataset.abc123
pltr dataset schema apply ri.foundry.main.dataset.abc123
pltr dataset schema set ri.foundry.main.dataset.abc123 --json-file schema.json
```

## Preview Data

```bash
# Preview dataset contents
pltr dataset preview DATASET_RID [--limit N]

# Examples
pltr dataset preview ri.foundry.main.dataset.abc123
pltr dataset preview ri.foundry.main.dataset.abc123 --limit 50
pltr dataset preview ri.foundry.main.dataset.abc123 --format csv --output preview.csv
```

## Transaction Operations

Transactions provide atomic operations with rollback capability.

```bash
# List transactions
pltr dataset transactions list DATASET_RID

# Start transaction
pltr dataset transactions start DATASET_RID [--branch BRANCH]

# Check transaction status
pltr dataset transactions status DATASET_RID TRANSACTION_RID

# Commit transaction
pltr dataset transactions commit DATASET_RID TRANSACTION_RID

# Abort transaction
pltr dataset transactions abort DATASET_RID TRANSACTION_RID

# Build information for a transaction
pltr dataset transactions build DATASET_RID TRANSACTION_RID
```

Transaction listing is dataset-wide because the pinned SDK transaction endpoint
does not expose a branch filter.

## Jobs and Schedules

```bash
# Jobs that ran against a dataset
pltr dataset jobs list DATASET_RID [--branch BRANCH] [--format FORMAT]

# Schedules that target a dataset
pltr dataset schedules list DATASET_RID [--format FORMAT]

# Examples
pltr dataset jobs list ri.foundry.main.dataset.abc123
pltr dataset schedules list ri.foundry.main.dataset.abc123 --format json
```

## View Operations

```bash
# List views (reports an explicit unsupported-capability warning with SDK 1.95.0)
pltr dataset views list DATASET_RID

# Create a view backed by DATASET_RID in the same parent folder
pltr dataset views create DATASET_RID VIEW_NAME

# View details
pltr dataset views get VIEW_RID [--branch BRANCH] [--format FORMAT]

# Manage backing datasets (comma-separated RIDs)
pltr dataset views add-datasets VIEW_RID DATASET_RID,DATASET_RID2
pltr dataset views remove-datasets VIEW_RID DATASET_RID,DATASET_RID2
pltr dataset views replace-datasets VIEW_RID DATASET_RID,DATASET_RID2

# Add a primary key (comma-separated fields)
pltr dataset views add-primary-key VIEW_RID KEY_FIELD,KEY_FIELD2

# Examples
pltr dataset views create ri.foundry.main.dataset.abc123 "analysis-view"
pltr dataset views get ri.foundry.main.view.abc123
pltr dataset views add-datasets ri.foundry.main.view.abc123 ri.foundry.main.dataset.def456
pltr dataset views add-primary-key ri.foundry.main.view.abc123 employee_id
```

`foundry-platform-sdk` 1.95.0 exposes `View.create` but not `View.list`, and
`View.create` has no description parameter. The CLI therefore fails closed when
`--description` is supplied instead of silently discarding it.

## Copy Datasets

```bash
# Copy dataset to another folder
pltr cp SOURCE_RID TARGET_FOLDER_RID [OPTIONS]

# Options:
#   --branch, -b TEXT     Dataset branch [default: master]
#   --recursive, -r       Required for folders
#   --name-suffix TEXT    Suffix for cloned names [default: -copy]
#   --schema/--no-schema  Copy schemas [default: true]
#   --dry-run             Preview without writing
#   --fail-fast           Stop on first error

# Examples
pltr cp ri.foundry.main.dataset.abc123 ri.compass.main.folder.dest456
pltr cp ri.compass.main.folder.source789 ri.compass.main.folder.dest456 --recursive
pltr cp ri.foundry.main.dataset.abc123 ri.compass.main.folder.dest456 --dry-run
```

## Common Patterns

### Download all files from a dataset
```bash
# List files, then download each
for file in $(pltr dataset files list ri.foundry.main.dataset.abc123 --format json | jq -r '.[].path'); do
  pltr dataset files get ri.foundry.main.dataset.abc123 "$file" "./${file##*/}"
done
```

### Export dataset info to JSON
```bash
pltr dataset get ri.foundry.main.dataset.abc123 --format json --output dataset-info.json
```
