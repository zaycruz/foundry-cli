# MediaSets Commands

Manage media sets and media content with transaction-based operations.

## RID Formats
- Media Sets: `ri.mediasets.main.media-set.{uuid}`
- Media Items: `ri.mediasets.main.media-item.{uuid}`

## Get Media Item Info

```bash
foundry media-sets get MEDIA_SET_RID MEDIA_ITEM_RID [--preview] [--format FORMAT]

# Example
foundry media-sets get ri.mediasets.main.media-set.abc123 ri.mediasets.main.media-item.def456
```

## Get Media Item by Path

```bash
foundry media-sets get-by-path MEDIA_SET_RID MEDIA_ITEM_PATH [--branch BRANCH] [--preview]

# Example
foundry media-sets get-by-path ri.mediasets.main.media-set.abc123 "/images/photo.jpg"
```

## Get Media Reference

Get embedding reference for a media item:

```bash
foundry media-sets reference MEDIA_SET_RID MEDIA_ITEM_RID [--preview] [--format FORMAT]

# Example
foundry media-sets reference ri.mediasets.main.media-set.abc123 ri.mediasets.main.media-item.def456
```

## Transaction Management

MediaSets use transactions for uploads.

Note on `--preview`: it enables Foundry preview APIs (passed through to the
SDK's `preview` parameter) — it is NOT a dry-run. Transactions created,
committed, or aborted with `--preview` still take effect.

### Create Transaction

```bash
foundry media-sets create MEDIA_SET_RID [--branch BRANCH] [--preview]

# Example
foundry media-sets create ri.mediasets.main.media-set.abc123 --branch main
# Prints a status line: "Transaction ID: <id>"
```

There is no `--format` option. The transaction ID is printed as a status
line (`Transaction ID: <id>`), which goes to stderr when stdout is piped
(see `src/foundry_cli/utils/formatting.py`). Capture it in scripts with:

```bash
TRANSACTION_ID=$(foundry media-sets create $MEDIA_SET 2>&1 | sed -n 's/.*Transaction ID: //p')
```

### Commit Transaction

```bash
foundry media-sets commit MEDIA_SET_RID TRANSACTION_ID [--preview] [--yes]

# Example
foundry media-sets commit ri.mediasets.main.media-set.abc123 transaction-id-12345 --yes
```

### Abort Transaction

```bash
foundry media-sets abort MEDIA_SET_RID TRANSACTION_ID [--preview] [--yes]

# Example
foundry media-sets abort ri.mediasets.main.media-set.abc123 transaction-id-12345 --yes
```

## Upload Media

```bash
foundry media-sets upload MEDIA_SET_RID FILE_PATH MEDIA_ITEM_PATH TRANSACTION_ID [--preview]

# Example
foundry media-sets upload ri.mediasets.main.media-set.abc123 \
  /local/path/image.jpg "/media/images/image.jpg" transaction-id-12345
```

## Download Media

```bash
foundry media-sets download MEDIA_SET_RID MEDIA_ITEM_RID OUTPUT_PATH [OPTIONS]

# Options:
#   --original      Download original version
#   --overwrite     Overwrite existing file
#   --preview       Enable preview mode

# Examples
foundry media-sets download ri.mediasets.main.media-set.abc123 \
  ri.mediasets.main.media-item.def456 /local/download/image.jpg

# Download original version
foundry media-sets download ri.mediasets.main.media-set.abc123 \
  ri.mediasets.main.media-item.def456 /local/download/original.jpg --original
```

## Thumbnail Operations

Generate and retrieve thumbnails for images (200px wide webp format).

### Calculate Thumbnail

Initiate thumbnail generation for an image:

```bash
foundry media-sets thumbnail-calculate MEDIA_SET_RID MEDIA_ITEM_RID [OPTIONS]

# Options:
#   --preview       Enable preview mode
#   --format        Output format (table, json, csv)
#   --output        Output file path

# Example
foundry media-sets thumbnail-calculate ri.mediasets.main.media-set.abc123 \
  ri.mediasets.main.media-item.def456
```

### Retrieve Thumbnail

Download a calculated thumbnail:

```bash
foundry media-sets thumbnail-retrieve MEDIA_SET_RID MEDIA_ITEM_RID OUTPUT_PATH [OPTIONS]

# Options:
#   --preview       Enable preview mode
#   --overwrite     Overwrite existing file

# Example
foundry media-sets thumbnail-retrieve ri.mediasets.main.media-set.abc123 \
  ri.mediasets.main.media-item.def456 /local/thumbnail.webp
```

## Upload Temporary Media

Upload temporary media that will be auto-deleted after 1 hour if not persisted:

```bash
foundry media-sets upload-temp FILE_PATH [OPTIONS]

# Options:
#   --filename      Override filename for the upload
#   --attribution   Attribution string for the media
#   --preview       Enable preview mode
#   --format        Output format (table, json, csv)
#   --output        Output file path

# Example
foundry media-sets upload-temp /local/image.jpg --attribution "Photo by John Doe"
```

## MediaSets Workflow

The typical upload workflow:

```bash
MEDIA_SET="ri.mediasets.main.media-set.abc123"

# 1. Create a transaction
TRANSACTION_ID=$(foundry media-sets create $MEDIA_SET 2>&1 | sed -n 's/.*Transaction ID: //p')
echo "Transaction: $TRANSACTION_ID"

# 2. Upload files within the transaction
foundry media-sets upload $MEDIA_SET /local/image1.jpg "/images/image1.jpg" $TRANSACTION_ID
foundry media-sets upload $MEDIA_SET /local/image2.jpg "/images/image2.jpg" $TRANSACTION_ID
foundry media-sets upload $MEDIA_SET /local/doc.pdf "/documents/doc.pdf" $TRANSACTION_ID

# 3. Commit the transaction (makes uploads available)
foundry media-sets commit $MEDIA_SET $TRANSACTION_ID --yes

echo "Upload complete!"
```

## Common Patterns

### Upload single file
```bash
MEDIA_SET="ri.mediasets.main.media-set.abc123"

# Create transaction
TX=$(foundry media-sets create $MEDIA_SET 2>&1 | sed -n 's/.*Transaction ID: //p')

# Upload
foundry media-sets upload $MEDIA_SET /path/to/file.jpg "/uploads/file.jpg" $TX

# Commit
foundry media-sets commit $MEDIA_SET $TX --yes
```

### Batch upload with error handling
```bash
MEDIA_SET="ri.mediasets.main.media-set.abc123"
TX=$(foundry media-sets create $MEDIA_SET 2>&1 | sed -n 's/.*Transaction ID: //p')

# Upload multiple files
for file in /local/images/*.jpg; do
  filename=$(basename "$file")
  if foundry media-sets upload $MEDIA_SET "$file" "/images/$filename" $TX; then
    echo "Uploaded: $filename"
  else
    echo "Failed: $filename"
    foundry media-sets abort $MEDIA_SET $TX --yes
    exit 1
  fi
done

# Commit if all successful
foundry media-sets commit $MEDIA_SET $TX --yes
```

### Download media by path
```bash
MEDIA_SET="ri.mediasets.main.media-set.abc123"

# Get media item RID by path
ITEM_RID=$(foundry media-sets get-by-path $MEDIA_SET "/images/photo.jpg" --format json | jq -r '.rid')

# Download
foundry media-sets download $MEDIA_SET $ITEM_RID ./downloaded_photo.jpg
```
