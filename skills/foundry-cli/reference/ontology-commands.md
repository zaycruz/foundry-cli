# Ontology Commands

Work with Foundry ontologies, object types, objects, actions, and queries.

## RID Format
`ri.ontology.main.ontology.{uuid}`

## List Ontologies

```bash
foundry ontology list [--format FORMAT] [--output FILE]

# Example
foundry ontology list --format table
```

## Get Ontology Details

```bash
foundry ontology get ONTOLOGY_RID [--format FORMAT]

# Example
foundry ontology get ri.ontology.main.ontology.abc123
```

## Resolve the Ontology RID

```bash
foundry ontology rid [--format FORMAT]

# Prints the ontology RID for this stack. Succeeds only when exactly one
# ontology is visible; zero or multiple visible ontologies fail loudly
# instead of guessing.

# Example
foundry ontology rid
```

## Required Publication Order

Ontology contract changes must be published in this order:

1. Modify backing dataset schemas (`foundry dataset schema update` / `foundry dataset schema set`; see dataset-commands.md).
2. Implement transaction functions.
3. `object-type-upsert` — create object types; `object-type-add-property` — add properties (with column mappings) to existing object types.
4. `link-type-upsert` — create link types between existing object types.
5. `action-type-upsert` — create action types; `action-type-update` — evolve existing action types (function rules, parameters, status).
6. Validate actions and re-read test objects.
7. Regenerate OSDK.
8. Enable the corresponding application controls.

Each upsert command's help text names its step, and dry-run validation
errors for missing dependencies (for example an action type referencing an
object type that does not exist yet) include a hint pointing back at this
sequence. Deletes run in reverse: `action-type-delete` (step 5), then
`link-type-delete` (step 4), then `object-type-delete` (step 3).

## Object Type Commands

### List Object Types

```bash
foundry ontology object-type-list ONTOLOGY_RID [--format FORMAT]

# Example
foundry ontology object-type-list ri.ontology.main.ontology.abc123
```

### Get Object Type Details

```bash
foundry ontology object-type-get ONTOLOGY_RID OBJECT_TYPE

# OBJECT_TYPE is the API name

# Example
foundry ontology object-type-get ri.ontology.main.ontology.abc123 Employee
```

### Create Object Type

```bash
foundry ontology object-type-create ONTOLOGY_RID \
    --api-name API_NAME --display-name NAME --primary-key FIELD \
    --backing-dataset DATASET_RID [--description TEXT]

# All of --api-name, --display-name, --primary-key and --backing-dataset
# are required.

# Example
foundry ontology object-type-create ri.ontology.main.ontology.abc123 \
    --api-name Employee --display-name "Employee" --primary-key employeeId \
    --backing-dataset ri.foundry.main.dataset.abc123
```

### Upsert Object Type (modifyOntology, plan-first)

```bash
foundry ontology object-type-upsert ONTOLOGY_RID \
    --api-name API_NAME --display-name NAME --primary-key FIELD \
    --backing-dataset DATASET_RID [--description TEXT] [--apply]

# Default is a dry-run plan of the modifyOntology write; nothing is written
# without --apply. --display-name, --primary-key and --backing-dataset are
# all required. When the object type already exists, the command switches to
# the update path: it loads the type's current state, merges the provided
# display name / description onto it, and issues an update modification --
# primary key and backing dataset must match the existing type, and the
# result reports the changed fields. Step 3 of the required publication
# order (see "Required Publication Order" above); steps 1-2 (backing
# dataset schema, transaction functions) must be done first.

# Example
foundry ontology object-type-upsert ri.ontology.main.ontology.abc123 \
    --api-name Employee --display-name "Employee" --primary-key employeeId \
    --backing-dataset ri.foundry.main.dataset.abc123 --apply
```

### Guarded Upsert Object Type (composite: preflight + impact gate + upsert + read-back)

```bash
foundry ontology object-type-guarded-upsert ONTOLOGY_RID \
    --api-name API_NAME --display-name NAME --primary-key FIELD \
    --backing-dataset DATASET_RID [--description TEXT] \
    [--change TEXT] [--change-type TYPE] [--skip-impact-gate] \
    [--graph-output FILE] [--apply] [--yes]

# Composite of the sequence agents otherwise run by hand: load current
# object type state -> dependency impact assessment (same engine as
# `foundry dependency object-type`) -> dry-run upsert plan -> on --apply,
# the upsert -> authoritative read-back. Default is plan-only; nothing is
# written without --apply. When the impact status is needs-verification
# with unresolved must_verify_before_merge items, --yes is additionally
# required and the acceptance is recorded in the result. For a net-new
# object type the gate is skipped with a recorded caveat (no existing
# dependents). --skip-impact-gate opts out explicitly and is recorded.
# Coverage gaps (partial/inaccessible/unsupported/unresolved/...) are
# carried as caveats in the result, never treated as "no impact".
# --change-type accepts the same enum as `foundry dependency object-type`:
# rename, type-change, optional-to-required, required-to-optional,
# remove-delete, action-input-change, query-output-change. --graph-output
# retains the full impact graph artifact. No --branch-rid: the underlying
# upsert writes to the default branch.

# Example
foundry ontology object-type-guarded-upsert ri.ontology.main.ontology.abc123 \
    --api-name Employee --display-name "Employee" --primary-key employeeId \
    --backing-dataset ri.foundry.main.dataset.abc123 \
    --change "rename display name" --change-type rename \
    --graph-output ./guarded-upsert-impact.json --apply
```

### Delete Object Type (modifyOntology, plan-first)

```bash
foundry ontology object-type-delete ONTOLOGY_RID OBJECT_TYPE_ID [--apply] [--yes]

# DESTRUCTIVE. Default is a dry-run plan; the real delete requires both
# --apply and --yes. OBJECT_TYPE_ID is the internal ObjectTypeId
# (e.g. 'ns1exmpl.employee'), not the API name or RID -- resolve it via
# `foundry ontology resolve` (see "Resolve Identifiers" below). Deletes run in
# reverse publication order: remove dependent action types (step 5) and
# link types (step 4) first.

# Example
foundry ontology object-type-delete ri.ontology.main.ontology.abc123 \
    ns1exmpl.employee --apply --yes
```

### Guarded Delete Object Type (composite: preflight + impact gate + delete + verify-removed)

```bash
foundry ontology object-type-guarded-delete ONTOLOGY_RID OBJECT_TYPE_ID \
    [--change TEXT] [--change-type TYPE] [--skip-impact-gate] \
    [--graph-output FILE] [--apply] [--yes]

# DESTRUCTIVE. Composite of the safe-delete sequence: preflight load of
# the object type (typed not-found aborts before any plan) -> dependency
# impact assessment (same engine as `foundry dependency object-type`;
# --change-type defaults to remove-delete) -> dry-run delete plan -> on
# --apply AND --yes, the delete -> read-back that confirms the type no
# longer loads (readback status verified-removed vs not-verified).
# OBJECT_TYPE_ID is the internal ObjectTypeId (e.g. 'ns1exmpl.employee'),
# resolvable via `foundry ontology resolve`. When the impact status is
# needs-verification, the confirmation names the unresolved
# must_verify_before_merge count and --yes is recorded as accepted.
# --skip-impact-gate opts out explicitly and is recorded. Coverage gaps
# are carried as caveats, never treated as "no impact".

# Example
foundry ontology object-type-guarded-delete ri.ontology.main.ontology.abc123 \
    ns1exmpl.employee --graph-output ./guarded-delete-impact.json \
    --apply --yes
```

### Add Property to Existing Object Type (modifyOntology, plan-first)

```bash
foundry ontology object-type-add-property ONTOLOGY_RID \
    --object-type OBJECT_TYPE_API_NAME_OR_RID \
    --api-name PROPERTY_API_NAME --type TYPE \
    [--display-name NAME] [--description TEXT] [--status STATUS] \
    [--visibility NORMAL|HIDDEN|PROMINENT] \
    [--backing-column COLUMN] [--backing-dataset DATASET_RID] \
    [--branch-rid ONTOLOGY_BRANCH_RID] [--apply]

# Default is a dry-run plan; nothing is written without --apply.
# Maps the new property to a backing dataset column (the column must exist:
# migrate the dataset schema first -- step 1 of the publication order).
# On --apply the property is read back and its RID returned.
# --branch-rid targets a non-default ontology branch (ontologyBranchRid).

# Example
foundry ontology object-type-add-property ri.ontology.main.ontology.abc123 \
    --object-type Cohort --api-name capacity --type INTEGER \
    --backing-column capacity --apply
```

### Update Existing Action Type (modifyOntology, plan-first)

```bash
foundry ontology action-type-update ONTOLOGY_RID \
    --action-type ACTION_TYPE_API_NAME_OR_RID \
    --definition PATCH_JSON_FILE   # or '-' for stdin \
    [--branch BRANCH] [--branch-rid ONTOLOGY_BRANCH_RID] [--apply]

# Partial patch over the existing action type. Supported keys: logic
# (including replacing object-edit rules with a function rule), parameters
# (add/remove/reorder; bind a parameter to the protected currentUser value),
# validations (submission criteria), write authorization, status
# (EXPERIMENTAL -> ACTIVE), displayMetadata. Unknown keys fail loudly.
# Default is a dry-run; on --apply the full metadata is read back and
# returned. Step 5 of the required publication order.

# Example
foundry ontology action-type-update ri.ontology.main.ontology.abc123 \
    --action-type create-cohort --definition patch.json --apply
```

### Resolve Identifiers (read-only)

```bash
foundry ontology resolve ONTOLOGY_RID --kind KIND \
    [--api-name API_NAME | --rid RID] [--object-type OBJECT_TYPE] [--version V]

# KIND: object-type | property | action-type | function.
# Returns the RID AND the internal ID (e.g. ObjectTypeId "ns0abcde.cohort")
# so you never probe internal bulk-load endpoints by hand.
# Property resolution is scoped with --object-type. --version is recorded
# but not resolved (the search gateway exposes no per-version RIDs).

# Examples
foundry ontology resolve ri.ontology.main.ontology.abc123 --kind object-type --api-name Cohort
foundry ontology resolve ri.ontology.main.ontology.abc123 --kind action-type --api-name create-cohort
foundry ontology resolve ri.ontology.main.ontology.abc123 --kind property --object-type Cohort --api-name capacity
```

## Object Commands

### List Objects

```bash
foundry ontology object-list ONTOLOGY_RID OBJECT_TYPE [OPTIONS]

# Options:
#   --page-size INTEGER    Results per page
#   --max-pages INTEGER    Maximum number of pages to fetch (default: 1)
#   --page-token TEXT      Page token to resume from a previous response
#   --all                  Fetch all available pages (overrides --max-pages)
#   --properties TEXT      Comma-separated properties to include

# Example
foundry ontology object-list ri.ontology.main.ontology.abc123 Employee
foundry ontology object-list ri.ontology.main.ontology.abc123 Employee --properties "name,department,email"
```

### Get Specific Object

```bash
foundry ontology object-get ONTOLOGY_RID OBJECT_TYPE PRIMARY_KEY [--properties TEXT]

# Example
foundry ontology object-get ri.ontology.main.ontology.abc123 Employee "john.doe"
```

### Aggregate Objects

```bash
foundry ontology object-aggregate ONTOLOGY_RID OBJECT_TYPE AGGREGATIONS [OPTIONS]

# AGGREGATIONS is JSON
# Options:
#   --group-by TEXT    Fields to group by (comma-separated)
#   --filter TEXT      Filter criteria (JSON)

# Example - Count by department
foundry ontology object-aggregate ri.ontology.main.ontology.abc123 Employee '{"count": "count"}' --group-by department
```

### List Linked Objects

```bash
foundry ontology object-linked ONTOLOGY_RID OBJECT_TYPE PRIMARY_KEY LINK_TYPE [--properties TEXT]

# Example
foundry ontology object-linked ri.ontology.main.ontology.abc123 Employee "john.doe" worksIn
```

### Count Objects

```bash
foundry ontology object-count ONTOLOGY_RID OBJECT_TYPE [--branch BRANCH]

# Example
foundry ontology object-count ri.ontology.main.ontology.abc123 Employee
```

### Search Objects

```bash
foundry ontology object-search ONTOLOGY_RID OBJECT_TYPE --query TEXT \
    [--properties TEXT] [--page-size N] [--branch BRANCH]

# Example
foundry ontology object-search ri.ontology.main.ontology.abc123 Employee --query "engineer"
```

## Link Type Commands

### Get Link Type Details

```bash
foundry ontology link-type-get ONTOLOGY_RID OBJECT_TYPE LINK_TYPE [--format FORMAT]

# OBJECT_TYPE and LINK_TYPE are API names; reads one outgoing link type of
# the object type

# Example
foundry ontology link-type-get ri.ontology.main.ontology.abc123 Employee worksIn
```

### Create Link Type

```bash
foundry ontology link-type-create ONTOLOGY_RID \
    --api-name API_NAME --from OBJECT_TYPE --to OBJECT_TYPE \
    [--display-name NAME] [--description TEXT] [--reverse-api-name NAME]

# Example
foundry ontology link-type-create ri.ontology.main.ontology.abc123 \
    --api-name worksIn --from Employee --to Department
```

### Upsert Link Type (modifyOntology, plan-first)

```bash
foundry ontology link-type-upsert ONTOLOGY_RID \
    --api-name API_NAME --from-object-type-id ID --to-object-type-id ID \
    [--display-name NAME] [--reverse-api-name NAME] \
    [--one-side-primary-key FIELD] [--many-side-property PROPERTY] \
    [--description TEXT] [--apply]

# Creates a one-to-many link type. Default is a dry-run plan; nothing is
# written without --apply. --from-object-type-id / --to-object-type-id take
# the internal ObjectTypeIds (e.g. 'ns1exmpl.employee'), not RIDs -- resolve
# them via `foundry ontology resolve` (see "Resolve Identifiers" below).
# Existing link types are NOT updated yet; the create validation reports
# that case explicitly. Step 4 of the required publication order -- both
# object types must already exist (step 3).

# Example
foundry ontology link-type-upsert ri.ontology.main.ontology.abc123 \
    --api-name worksIn \
    --from-object-type-id ns1exmpl.department \
    --to-object-type-id ns1exmpl.employee \
    --many-side-property departmentId --apply
```

### Delete Link Type (modifyOntology, plan-first)

```bash
foundry ontology link-type-delete ONTOLOGY_RID LINK_TYPE_ID [--apply] [--yes]

# DESTRUCTIVE. Default is a dry-run plan; the real delete requires both
# --apply and --yes. LINK_TYPE_ID is the internal LinkTypeId
# (e.g. 'ns1exmpl.works-in'), not the API name or RID. Deletes run in
# reverse publication order: link types (step 4) go after dependent action
# types (step 5), before object types (step 3).

# Example
foundry ontology link-type-delete ri.ontology.main.ontology.abc123 \
    ns1exmpl.works-in --apply --yes
```

## Action Commands

### Get Action Type Details

```bash
foundry ontology action-type-get ONTOLOGY_RID ACTION_TYPE [--branch BRANCH]

# ACTION_TYPE is the API name; read-only full metadata (preview-gated endpoint)

# Example
foundry ontology action-type-get ri.ontology.main.ontology.abc123 modify-example
```

### Apply Action

```bash
foundry ontology action-apply ONTOLOGY_RID ACTION_TYPE PARAMETERS

# PARAMETERS is JSON

# Example
foundry ontology action-apply ri.ontology.main.ontology.abc123 promoteEmployee '{"employeeId": "john.doe", "newLevel": "senior"}'
```

### Validate Action

Validate parameters without executing:

```bash
foundry ontology action-validate ONTOLOGY_RID ACTION_TYPE PARAMETERS

# Example
foundry ontology action-validate ri.ontology.main.ontology.abc123 promoteEmployee '{"employeeId": "john.doe", "newLevel": "senior"}'
```

### Upsert Action Type (modifyOntology, plan-first)

```bash
foundry ontology action-type-upsert ONTOLOGY_RID --definition ACTION_TYPE_CREATE_JSON_FILE [--apply]

# --definition is a plain path to a JSON file containing the
# ActionTypeCreate document; '-' reads stdin (there is no @file expansion
# or inline JSON). Default is a dry-run plan; nothing is written without
# --apply. Existing action types are NOT updated yet; the create validation
# reports that case explicitly. Step 5 of the required publication order --
# referenced object types (step 3) and link types (step 4) must already
# exist; steps 6-8 (validate actions, regenerate OSDK, enable application
# controls) follow.

# Example
foundry ontology action-type-upsert ri.ontology.main.ontology.abc123 \
    --definition action-type.json --apply
```

### Delete Action Type (modifyOntology, plan-first)

```bash
foundry ontology action-type-delete ONTOLOGY_RID ACTION_TYPE [--apply] [--yes]

# DESTRUCTIVE. Default is a dry-run plan; the real delete requires both
# --apply and --yes. Deletes run in reverse publication order: action types
# (step 5) are deleted first.

# Example
foundry ontology action-type-delete ri.ontology.main.ontology.abc123 \
    promote-employee --apply --yes
```

## Query Commands

### Execute Predefined Query

```bash
foundry ontology query-execute ONTOLOGY_RID QUERY_NAME [--parameters JSON]

# Example
foundry ontology query-execute ri.ontology.main.ontology.abc123 getEmployeesByDepartment --parameters '{"department": "Engineering"}'
```

## Common Patterns

### Explore an ontology
```bash
ONTOLOGY="ri.ontology.main.ontology.abc123"

# List all object types
foundry ontology object-type-list $ONTOLOGY

# Get details of a specific type
foundry ontology object-type-get $ONTOLOGY Employee

# List objects with specific properties
foundry ontology object-list $ONTOLOGY Employee --properties "name,department,startDate"
```

### Get employee and their projects
```bash
ONTOLOGY="ri.ontology.main.ontology.abc123"

# Get employee
foundry ontology object-get $ONTOLOGY Employee "john.doe"

# Get linked projects
foundry ontology object-linked $ONTOLOGY Employee "john.doe" worksOn --properties "name,status,deadline"
```

### Department statistics
```bash
foundry ontology object-aggregate ri.ontology.main.ontology.abc123 Employee \
  '{"count": "count", "avg_salary": "avg"}' \
  --group-by department \
  --format csv --output department_stats.csv
```

### Export employees to JSON
```bash
foundry ontology object-list ri.ontology.main.ontology.abc123 Employee \
  --properties "name,department,email,startDate" \
  --format json --output employees.json
```
