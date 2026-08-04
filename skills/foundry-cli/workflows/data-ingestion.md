# Data Ingestion Workflows

Three ingestion paths: batch file upload via dataset transactions, connectivity imports from external systems, and streaming publish. Choose by source shape: files on disk → transactions, an existing external system connection → connectivity imports, continuous records → streams.

Before ingesting into a dataset with downstream consumers, run `workflows/change-impact-assessment.md` against the target resource. Ingestion mutations in this file are plan-first: inspect first, mutate only with explicit intent, and keep rollback available.

## Path A: Batch File Upload via Dataset Transactions

Transactions give atomic visibility: files uploaded inside an open transaction become visible only on commit. Abort discards them.

### Phase 1: Preflight

```bash
foundry verify --profile "$PROFILE"
foundry dataset get ri.foundry.main.dataset.abc123 --profile "$PROFILE"
foundry dataset files list ri.foundry.main.dataset.abc123 --branch master
```

Confirm the dataset RID, the target branch, and the current file set before opening a transaction.

### Phase 2: Start a transaction

```bash
# Append new files (default type)
foundry dataset transactions start ri.foundry.main.dataset.abc123 \
  --branch master --type APPEND --format json

# Idempotent full replace: rerun-safe, the new view replaces the old
foundry dataset transactions start ri.foundry.main.dataset.abc123 \
  --branch master --type SNAPSHOT --format json
```

Transaction types: `APPEND` (add files), `UPDATE` (add and overwrite), `SNAPSHOT` (replace the entire file view), `DELETE` (remove files). Prefer `SNAPSHOT` for scheduled re-ingestion: a rerun produces the same end state instead of duplicating files.

Capture the transaction RID from the JSON response.

### Phase 3: Upload files into the transaction

```bash
foundry dataset files upload "./export_001.csv" ri.foundry.main.dataset.abc123 \
  --branch master --transaction-rid ri.foundry.main.transaction.xyz789
```

Repeat per file. An upload without `--transaction-rid` writes inside its own implicit transaction; always pass the RID explicitly for multi-file atomic loads.

### Phase 4: Check status, then commit or abort

```bash
# Inspect before committing
foundry dataset transactions status ri.foundry.main.dataset.abc123 \
  ri.foundry.main.transaction.xyz789 --format json

# Commit: publishes the transaction's files
foundry dataset transactions commit ri.foundry.main.dataset.abc123 \
  ri.foundry.main.transaction.xyz789

# Abort on any failure: discards uploaded files (rollback)
foundry dataset transactions abort ri.foundry.main.dataset.abc123 \
  ri.foundry.main.transaction.xyz789 --yes
```

There is no transaction dry-run; the plan-first gate is the status check before commit. `abort` prompts for confirmation unless `--yes` is passed; scripts should pass `--yes` so rollback never blocks on a prompt.

Notes:

- `foundry dataset transactions list` is dataset-wide; the pinned SDK transaction endpoint has no branch filter.
- After commit, verify with `foundry dataset files list` or `foundry dataset stats DATASET_RID --branch master`.

## Path B: Connectivity Imports

Use this path when data arrives through a Data Connection source. The CLI surface for imports is inspection-only.

```bash
# Find the connection
foundry connectivity connection list --format json --output connections.json
foundry connectivity connection get ri.conn.main.connection.12345

# Inventory existing imports on the connection
foundry connectivity import list-file --connection ri.conn.main.connection.12345
foundry connectivity import list-table --connection ri.conn.main.connection.12345

# Inspect a specific import (target dataset, sync mode, status)
foundry connectivity import get-table ri.import.main.table.456 \
  --connection ri.conn.main.connection.12345 --format json
```

Capability gap (also noted in `workflows/data-pipeline.md`): the pinned SDK requires connection-specific typed models to create imports, so generic file/table import creation is not exposed in this CLI. Create and configure new imports in the Foundry Data Connection UI, then use the commands above to inventory and inspect them. Do not guess at an import-create command.

## Path C: Streaming Publish

Use streams for continuous record-level ingestion. Streams are not transactional: publish is at-least-once, and rollback is not available after publish. Idempotency must come from a dedupe key in the record schema that downstream transforms can deduplicate on.

```bash
# 1. Create the streaming dataset with its initial stream (mutating; no dry-run —
#    confirm NAME, folder RID, and schema before running)
foundry streams dataset create events \
  --folder ri.compass.main.folder.xyz789 \
  --schema '{"fieldSchemaList": [{"name": "event_id", "type": "STRING"}, {"name": "timestamp", "type": "TIMESTAMP"}, {"name": "data", "type": "STRING"}]}'

# 2. Confirm the stream exists on the branch
foundry streams stream get ri.foundry.main.dataset.abc123 --branch master --format json

# 3. Publish records — prefer batches over per-record calls
foundry streams stream publish-batch ri.foundry.main.dataset.abc123 \
  --branch master \
  --records '[{"event_id": "evt-001", "timestamp": 1735689600, "data": "payload"}]'

# Single record when needed
foundry streams stream publish ri.foundry.main.dataset.abc123 \
  --branch master --record @record.json
```

For volume, size partitions up front: each partition handles roughly 5 MB/s (`--partitions N --type HIGH_THROUGHPUT` on `streams dataset create`). To add a stream on another branch of an existing dataset, use `foundry streams stream create DATASET_RID --branch BRANCH --schema SCHEMA`.

## End-to-End Idempotent Ingest Script

Full batch load with rollback: a failed run aborts its transaction and leaves the dataset untouched; a rerun with `SNAPSHOT` converges to the same end state.

```bash
#!/bin/bash
# ingest.sh - Idempotent batch ingest with transaction rollback
# Usage: DATASET_RID=... BRANCH=master PROFILE=default ./ingest.sh ./data/*.csv
set -euo pipefail

DATASET_RID="${DATASET_RID:?Set DATASET_RID (e.g. ri.foundry.main.dataset.abc123)}"
BRANCH="${BRANCH:-master}"
PROFILE="${PROFILE:-default}"
FILES=("$@")
[ "${#FILES[@]}" -gt 0 ] || { echo "No input files given"; exit 1; }

TRANSACTION_RID=""

rollback() {
  if [ -n "$TRANSACTION_RID" ]; then
    echo "Rolling back transaction $TRANSACTION_RID"
    foundry dataset transactions abort "$DATASET_RID" "$TRANSACTION_RID" \
      --yes --profile "$PROFILE" || echo "WARN: abort failed; transaction may remain open"
  fi
}
trap rollback ERR

# 1. Preflight
foundry verify --profile "$PROFILE"
foundry dataset get "$DATASET_RID" --profile "$PROFILE" >/dev/null

# 2. Start a SNAPSHOT transaction (rerun-safe full replace)
#    Adjust the jq field to the RID field in the observed JSON response.
TRANSACTION_RID=$(foundry dataset transactions start "$DATASET_RID" \
  --branch "$BRANCH" --type SNAPSHOT --format json --profile "$PROFILE" \
  | jq -r '.rid')
echo "Opened transaction $TRANSACTION_RID"

# 3. Upload all files into the transaction
for f in "${FILES[@]}"; do
  echo "Uploading $f"
  foundry dataset files upload "$f" "$DATASET_RID" \
    --branch "$BRANCH" --transaction-rid "$TRANSACTION_RID" \
    --profile "$PROFILE"
done

# 4. Gate on status before commit
foundry dataset transactions status "$DATASET_RID" "$TRANSACTION_RID" \
  --format json --profile "$PROFILE"

# 5. Commit and disarm the rollback trap
foundry dataset transactions commit "$DATASET_RID" "$TRANSACTION_RID" \
  --profile "$PROFILE"
TRANSACTION_RID=""
trap - ERR

# 6. Post-commit verification
foundry dataset files list "$DATASET_RID" --branch "$BRANCH" --profile "$PROFILE"
echo "Ingest complete."
```

The script takes no confirmation flags itself because every mutation is either reversible (the transaction, aborted on error) or gated by the operator setting `DATASET_RID` explicitly. If the target dataset feeds downstream builds, run `workflows/change-impact-assessment.md` on the dataset before the first run.

## Best Practices

1. **Always upload inside an explicit transaction**: pass `--transaction-rid` for multi-file loads.
2. **Use SNAPSHOT for scheduled re-ingestion**: reruns converge instead of duplicating.
3. **Gate commit on status**: inspect the transaction before publishing it.
4. **Pass `--yes` to abort in scripts**: rollback must never block on a prompt.
5. **Batch stream publishes**: `publish-batch` over per-record `publish` loops.
6. **Dedupe in the stream schema**: publish is at-least-once; carry a stable record key.
7. **Verify after commit**: `dataset files list` or `dataset stats` against the branch.

## Anti-Patterns

- Uploading files one implicit transaction at a time and calling it atomic
- Committing without a status check, or aborting without `--yes` inside a trap
- Using `APPEND` for recurring full refreshes (duplicates accumulate)
- Inventing a connectivity import-create command; the pinned SDK does not expose one
- Treating stream publish as transactional or expecting rollback after publish
- Ingesting into a dataset with downstream consumers without a change-impact assessment
