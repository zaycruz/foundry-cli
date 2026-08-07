# Media Management Workflows

Locate, upload, and download media in Foundry MediaSets. Uploads are transaction-based: files are staged inside a transaction and only become visible when it is committed.

RID formats:

- Media Sets: `ri.mediasets.main.media-set.{uuid}`
- Media Items: `ri.mediasets.main.media-item.{uuid}`

Uploading to a MediaSet mutates a Foundry resource. Run `workflows/change-impact-assessment.md` against the MediaSet RID before committing changes to shared MediaSets.

## Locate Items

Resolve an item path to its RID, then inspect it:

```bash
MEDIA_SET="ri.mediasets.main.media-set.abc123"

# Look up an item by its path within the media set
pfoundry media-sets get-by-path "$MEDIA_SET" "/images/photo.jpg" \
  --profile "$PROFILE" --format json

# Capture the RID for scripting (JSON keys: path, rid)
ITEM_RID=$(foundry media-sets get-by-path "$MEDIA_SET" "/images/photo.jpg" \
  --profile "$PROFILE" --format json | jq -r '.rid')

# Get detailed info about the item
pfoundry media-sets get "$MEDIA_SET" "$ITEM_RID" \
  --profile "$PROFILE" --format json

# Look up on a non-default branch
pfoundry media-sets get-by-path "$MEDIA_SET" "/images/photo.jpg" \
  --branch "$BRANCH" --profile "$PROFILE"
```

## Embedding References

Get a reference to a media item for embedding in other Foundry resources:

```bash
pfoundry media-sets reference "$MEDIA_SET" "$ITEM_RID" \
  --profile "$PROFILE" --format json
```

## Transaction Lifecycle

Every upload to a MediaSet happens inside a transaction:

1. **Create**: `pfoundry media-sets create` opens a transaction and prints the transaction ID.
2. **Upload**: `pfoundry media-sets upload` stages one file per call into the transaction. Staged files are not visible to other consumers.
3. **Commit**: `pfoundry media-sets commit` makes all staged uploads available atomically. Prompts for confirmation unless `--yes` is passed.
4. **Abort**: `pfoundry media-sets abort` discards the transaction and deletes anything staged in it. Prompts for confirmation unless `--yes` is passed.

Rules:

- Never leave a transaction open after a failure: abort it. An aborted transaction is the only rollback mechanism; there is no way to un-commit.
- `commit` and `abort` are the mutating steps. In scripts, pass `--yes` explicitly; interactively, let the confirmation prompt stand.
- `pfoundry media-sets create` has no `--format` option. It prints `Transaction ID: <id>` as a status line; capture it by parsing the output.
- Status lines go to stderr when stdout is piped, so merge the streams when capturing:

```bash
TX=$(foundry media-sets create "$MEDIA_SET" --profile "$PROFILE" 2>&1 \
  | sed -n 's/.*Transaction ID: //p')
```

## Upload Scripts

### Single file

```bash
#!/bin/bash
# upload_one.sh - Upload one file into a MediaSet
set -e

MEDIA_SET="ri.mediasets.main.media-set.abc123"
PROFILE="production"

# 1. Create a transaction and capture its ID
TX=$(foundry media-sets create "$MEDIA_SET" --profile "$PROFILE" 2>&1 \
  | sed -n 's/.*Transaction ID: //p')
echo "Transaction: $TX"

# 2. Stage the file
pfoundry media-sets upload "$MEDIA_SET" ./report.pdf "/documents/report.pdf" "$TX" \
  --profile "$PROFILE"

# 3. Commit (explicit confirmation)
pfoundry media-sets commit "$MEDIA_SET" "$TX" --yes --profile "$PROFILE"

echo "Upload complete."
```

### End-to-end batch upload with abort-on-failure

```bash
#!/bin/bash
# upload_batch.sh - Upload a directory of files atomically.
# Any failed upload aborts the whole transaction: nothing partial is published.
set -e

MEDIA_SET="ri.mediasets.main.media-set.abc123"
PROFILE="production"
LOCAL_DIR="./images"
REMOTE_PREFIX="/images"
BRANCH="main"

# Abort helper: every failure path funnels here
abort_tx() {
  echo "Aborting transaction $TX: $1"
  pfoundry media-sets abort "$MEDIA_SET" "$TX" --yes --profile "$PROFILE"
  exit 1
}

# 1. Create the transaction
TX=$(foundry media-sets create "$MEDIA_SET" --branch "$BRANCH" --profile "$PROFILE" 2>&1 \
  | sed -n 's/.*Transaction ID: //p')
if [ -z "$TX" ]; then
  echo "ERROR: failed to create transaction"
  exit 1
fi
echo "Transaction: $TX"

# 2. Stage every file; abort the transaction on the first failure
for file in "$LOCAL_DIR"/*; do
  filename=$(basename "$file")
  if foundry media-sets upload "$MEDIA_SET" "$file" "$REMOTE_PREFIX/$filename" "$TX" \
      --profile "$PROFILE"; then
    echo "Staged: $filename"
  else
    abort_tx "upload failed for $filename"
  fi
done

# 3. Commit only when every file staged successfully
pfoundry media-sets commit "$MEDIA_SET" "$TX" --yes --profile "$PROFILE"

echo "Batch upload committed: $TX"
```

## Download Media

Downloads are keyed by media item RID, not path. Resolve the path first with `get-by-path` when needed.

```bash
# Download the processed rendition (default)
pfoundry media-sets download "$MEDIA_SET" "$ITEM_RID" ./photo.jpg \
  --profile "$PROFILE"

# Download the original rendition as uploaded
pfoundry media-sets download "$MEDIA_SET" "$ITEM_RID" ./photo-original.jpg \
  --original --profile "$PROFILE"

# Overwrite an existing local file
pfoundry media-sets download "$MEDIA_SET" "$ITEM_RID" ./photo.jpg \
  --overwrite --profile "$PROFILE"
```

Download by path:

```bash
ITEM_RID=$(foundry media-sets get-by-path "$MEDIA_SET" "/images/photo.jpg" \
  --profile "$PROFILE" --format json | jq -r '.rid')
pfoundry media-sets download "$MEDIA_SET" "$ITEM_RID" ./photo.jpg --profile "$PROFILE"
```

The processed rendition is the default because it is what Foundry renders (e.g. normalized images). Use `--original` when byte-exact fidelity with the uploaded file matters, such as archival or checksum verification.

## Capability Gaps

These operations are not exposed by `pfoundry media-sets`; do not guess at them:

- No command lists the items inside a MediaSet. Address items by known path (`get-by-path`) or by RID.
- No command deletes a MediaSet or an individual media item. Rollback of an uncommitted upload is `abort`; rollback after commit is not available from the CLI.
- No dry-run mode for uploads. `--preview` enables the Foundry preview APIs; it is not a dry-run. The plan-first control for uploads is the transaction lifecycle itself: stage, verify, then `commit` or `abort`.
- `pfoundry media-sets create` emits no machine-readable format; scripts must parse the `Transaction ID:` status line.

## Best Practices

1. **Always pair create with commit or abort**: never exit a script with an open transaction
2. **Abort on first failure**: partial uploads stay invisible; aborting keeps the MediaSet clean
3. **Pass `--yes` explicitly in scripts**: commit and abort prompt by default
4. **Verify auth first**: run `pfoundry verify` at script start
5. **Use `--format json` for lookups**: `get-by-path`, `get`, and `reference` support it for scripting
6. **Default to the processed rendition**: use `--original` only when byte-exact originals are required
