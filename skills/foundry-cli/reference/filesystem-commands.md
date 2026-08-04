# Filesystem Commands

Manage folders, spaces, projects, resources, and permissions.

## RID Formats
- Folders: `ri.compass.main.folder.{uuid}` (root: `ri.compass.main.folder.0`)
- Spaces: `ri.compass.main.space.{uuid}`
- Projects: `ri.compass.main.project.{uuid}`
- Resources: Various patterns depending on type

## Folder Commands

### Create Folder

```bash
foundry folder create NAME [--parent-folder FOLDER_RID] [--format FORMAT]

# Default parent is root: ri.compass.main.folder.0

# Example
foundry folder create "My Project"
foundry folder create "Sub Folder" --parent-folder ri.compass.main.folder.xyz123
```

### Get Folder Info

```bash
foundry folder get FOLDER_RID [--format FORMAT] [--output FILE]

# Example
foundry folder get ri.compass.main.folder.abc123
```

### List Folder Contents

```bash
foundry folder list FOLDER_RID [--page-size N] [--format FORMAT]

# Example - List root folder
foundry folder list ri.compass.main.folder.0

# List with pagination
foundry folder list ri.compass.main.folder.abc123 --page-size 50
```

### Batch Get Folders

```bash
foundry folder batch-get FOLDER_RIDS...

# Max 1000 RIDs

# Example
foundry folder batch-get ri.compass.main.folder.abc123 ri.compass.main.folder.def456
```

### Move Folder

```bash
foundry folder move FOLDER_RID [--parent-folder TARGET_FOLDER_RID] [--name NEW_NAME] [--confirm]

# Moves a folder to a new parent, optionally renaming it in the same call

# Example
foundry folder move ri.compass.main.folder.abc123 \
    --parent-folder ri.compass.main.folder.xyz789 --name "Archived Project"
```

## Space Commands

### Create Space

```bash
foundry space create DISPLAY_NAME [OPTIONS]

# Required Options:
#   --enrollment-rid, -e     Enrollment Resource Identifier
#   --organization, -org     Organization RID(s) (can specify multiple)
#   --deletion-policy-org    Organization RID(s) for deletion policy (can specify multiple)

# Optional:
#   --description TEXT       Space description

# Example
foundry space create "Data Science Team" \
  --enrollment-rid ri.enrollment.main.enrollment.abc123 \
  --organization ri.compass.main.organization.xyz456 \
  --deletion-policy-org ri.compass.main.organization.xyz456 \
  --description "Space for analytics work"
```

### Get Space

```bash
foundry space get SPACE_RID [--format FORMAT]
```

### List Spaces

```bash
foundry space list [--organization-rid RID] [--page-size N] [--format FORMAT]
```

### Update Space

```bash
foundry space update SPACE_RID [--display-name TEXT] [--description TEXT]
```

### Delete Space

```bash
foundry space delete SPACE_RID [--yes]
```

## Project Commands

### Create Project

```bash
foundry project create DISPLAY_NAME SPACE_RID [OPTIONS]

# Options:
#   --description TEXT         Project description
#   --organization-rids TEXT   Comma-separated org RIDs
#   --default-roles TEXT       Comma-separated default roles

# Example
foundry project create "ML Pipeline" ri.compass.main.space.abc123 \
  --description "Machine learning pipeline project"
```

### Other Project Commands

```bash
foundry project get PROJECT_RID
foundry project list [--space-rid RID]
foundry project imports PROJECT_RID [--reference-type EXTERNAL|FILESYSTEM] [--page-size N] [--page-token TOKEN]
foundry project search QUERY [--space-rid SPACE_RID] [--page-size N] [--page-token TOKEN]
foundry project templates list [--namespace-rid RID] [--page-size N] [--page-token TOKEN]
foundry project update PROJECT_RID [--display-name TEXT] [--description TEXT]
```

`project imports` uses the SDK's verified `Project.Reference.list` contract.
Project search is a bounded client-side filter over visible project metadata;
its continuation token is a RID keyset cursor, not a Foundry server token.
`project templates list` enumerates templates through the verified internal
Compass endpoint `GET /compass/api/templates/namespace/{namespaceRid}` —
across every visible namespace unless `--namespace-rid` narrows it. Without a
server page token both commands paginate with a client-side offset cursor.

## Namespace Discovery

```bash
foundry namespace list [--page-size N] [--page-token TOKEN] [--format agent]
```

SDK 1.95.0 has no Namespace resource, so this command uses the verified
internal Compass hierarchy endpoints (`GET
/compass/api/hierarchy/v2/all-namespace-rids` plus the `PUT
/compass/api/hierarchy/v2/batch/namespaces` read-batch hydration) and emits
records with `source_type: compass-namespace`. Namespaces the hydration
silently omits (permission filtering returns HTTP 200, never 403) are kept
with `hydrated: false` instead of being dropped.

### Add Organizations to Project

```bash
foundry project add-orgs PROJECT_RID --org ORG_RID [--org ORG_RID...]

# Example
foundry project add-orgs ri.compass.main.project.abc123 -o ri.compass.main.org.123 -o ri.compass.main.org.456
```

### Remove Organizations from Project

```bash
foundry project remove-orgs PROJECT_RID --org ORG_RID [--org ORG_RID...]

# Example
foundry project remove-orgs ri.compass.main.project.abc123 -o ri.compass.main.org.123
```

### List Project Organizations

```bash
foundry project list-orgs PROJECT_RID [--page-size N] [--format FORMAT]

# Example
foundry project list-orgs ri.compass.main.project.abc123 --format json
```

### Create Project from Template

```bash
foundry project create-from-template --template-rid TEMPLATE_RID --var "name=value" [OPTIONS]

# Options:
#   --template-rid, -t    Template RID (required)
#   --var, -v             Variable values in format 'name=value' (can specify multiple)
#   --description, -d     Project description
#   --org, -o             Organization RIDs (can specify multiple)

# Example
foundry project create-from-template -t ri.template.main.123 \
  -v "project_name=MyProject" \
  -v "environment=production" \
  -d "Project from template"
```

## Resource Graph

```bash
foundry lineage graph RESOURCE_RID \
  [--direction upstream|downstream|both] \
  [--max-depth N] [--max-nodes N] [--max-edges N] \
  [--page-size N] [--page-token TOKEN] [--format agent]
```

The graph is built from verified filesystem parent/child and project-reference
APIs. It is bounded and always reports incomplete coverage because the public
SDK has no transformation-lineage endpoint; it must not be treated as full
pipeline lineage.

## Cross-Resource and Notepad Discovery

```bash
# Legacy title search
foundry search "sales data" --limit 25 --format json

# Bounded path-scoped search
foundry search "sales" \
  --path-prefix "/Finance" \
  --resource-type Dataset \
  --page-size 100 \
  --format json

# Continue a path-scoped search
foundry search "sales" \
  --path-prefix "/Finance" \
  --page-size 100 \
  --page-token TOKEN \
  --format json

# Enumerate notepads from an explicit path
foundry notepad list --path-prefix "/Finance" --page-size 100 --format json

# Read one notepad's latest body and embedded resource references
foundry notepad get NOTEPAD_RID [--format FORMAT] [--output-mode MODE]
```

`search(title:)` is the legacy title-only operation. Path-scoped mode uses
`searchResources` with verified server-side `pathStartsWith` filtering.
`--page-token` accepts the prior response's `next_page_token`. Text and
`--type` constraints are applied locally to only the returned page, so
the result reports `coverage` and `server_page_count`. The gateway does not
report continuation state for legacy title search.

`notepad list` requires at least one `--path-prefix`; it never guesses an
instance root. It selects the live resource type `Notepad document`
case-insensitively from each returned page. Use `next_page_token` to continue.
Use `--format json` for machine-readable success output.

## Resource Commands

### Get Resource

```bash
foundry resource get RESOURCE_RID [--format FORMAT]
```

### Get Resource by Path

```bash
foundry resource get-by-path PATH [--format FORMAT]

# PATH is the absolute Compass path (e.g. "/Finance/sales-data")

# Example
foundry resource get-by-path "/Finance/sales-data" --format json
```

### List Resources

```bash
foundry resource list [--folder-rid RID] [--type TYPE] [--page-size N]

# Example
foundry resource list --folder-rid ri.compass.main.folder.abc123 --type dataset
```

### Search Resources

```bash
foundry resource search QUERY [--type TYPE] [--folder-rid RID]

# Example
foundry resource search "sales data" --type dataset
```

### Batch Get Resources

```bash
foundry resource batch-get RESOURCE_RIDS...
```

## Resource Lifecycle Commands

### Delete Resource (Move to Trash)

```bash
foundry resource delete RESOURCE_RID [--force]

# Example
foundry resource delete ri.foundry.main.dataset.abc123

# Skip confirmation prompt
foundry resource delete ri.foundry.main.dataset.abc123 --force
```

### Restore Resource from Trash

```bash
foundry resource restore RESOURCE_RID

# Example
foundry resource restore ri.foundry.main.dataset.abc123
```

### Permanently Delete Resource

```bash
foundry resource permanently-delete RESOURCE_RID [--force]

# WARNING: This action is irreversible!

# Example
foundry resource permanently-delete ri.foundry.main.dataset.abc123 --force
```

## Resource Markings Commands

### Add Markings to Resource

```bash
foundry resource add-markings RESOURCE_RID --marking MARKING_ID [--marking MARKING_ID...]

# Example - add single marking
foundry resource add-markings ri.foundry.main.dataset.abc123 -m marking-id-1

# Add multiple markings
foundry resource add-markings ri.foundry.main.dataset.abc123 -m marking-id-1 -m marking-id-2
```

### Remove Markings from Resource

```bash
foundry resource remove-markings RESOURCE_RID --marking MARKING_ID [--marking MARKING_ID...]

# Example
foundry resource remove-markings ri.foundry.main.dataset.abc123 -m marking-id-1 -m marking-id-2
```

### List Resource Markings

```bash
foundry resource list-markings RESOURCE_RID [--page-size N] [--format FORMAT]

# Example
foundry resource list-markings ri.foundry.main.dataset.abc123 --format json
```

### Get Access Requirements

```bash
foundry resource access-requirements RESOURCE_RID [--format FORMAT]

# Returns required organizations and markings for accessing a resource

# Example
foundry resource access-requirements ri.foundry.main.dataset.abc123 --format json
```

## Resource Path Operations

### Batch Get Resources by Path

```bash
foundry resource batch-get-by-path PATHS... [--format FORMAT]

# Get multiple resources by their absolute paths (max 1000)

# Example
foundry resource batch-get-by-path "/Org/Project/Dataset1" "/Org/Project/Dataset2"
```

## Resource Role Commands

### Grant Role

```bash
foundry resource-role grant RESOURCE_RID \
  --principal-id PRINCIPAL_UUID \
  --principal-type User|Group \
  --role ROLE_ID

# The pinned SDK requires a principal UUID.
```

### Revoke Role

```bash
foundry resource-role revoke RESOURCE_RID \
  --principal-id PRINCIPAL_UUID \
  --principal-type User|Group \
  --role ROLE_ID
```

### List Roles

```bash
foundry resource-role list RESOURCE_RID [--principal-type TYPE]

# Example
foundry resource-role list ri.foundry.main.dataset.abc123 --principal-type User
```

## Common Patterns

### Create workspace structure
```bash
# Create folders
ROOT=$(foundry folder create "Analytics Work" --format json | jq -r '.rid')
foundry folder create "Raw Data" --parent-folder $ROOT
foundry folder create "Processed" --parent-folder $ROOT
foundry folder create "Reports" --parent-folder $ROOT
```

### Set up team permissions
```bash
DATASET="ri.foundry.main.dataset.customer-data"
TEAM_UUID="12345678-1234-1234-1234-123456789abc"
USER_UUID="87654321-4321-4321-4321-cba987654321"

# Grant team access
foundry resource-role grant "$DATASET" \
  --principal-id "$TEAM_UUID" --principal-type Group --role ROLE_ID

# Grant individual access
foundry resource-role grant "$DATASET" \
  --principal-id "$USER_UUID" --principal-type User --role ROLE_ID
```

### Find resources
```bash
# Search for datasets
foundry resource search "sales" --type dataset --format json --output sales.json

# Get resource details
for rid in $(cat sales.json | jq -r '.[].rid'); do
  foundry resource get "$rid" --format json
done
```
