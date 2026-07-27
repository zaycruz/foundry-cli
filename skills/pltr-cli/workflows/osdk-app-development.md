# OSDK App Development Workflow

Build an OSDK application end-to-end: validate the app's dev-console context,
inspect the OSDK definition, generate and install SDK packages, scaffold typed
React components, clone the code repository, consult the documentation corpus,
and — when the app uses custom widgets — manage widget dev mode and releases.

Mutations are plan-first: generation and install default to dry-run plans and
require an explicit `--apply` or `--yes`. When a step changes a Foundry
resource, run [change-impact-assessment.md](change-impact-assessment.md)
before applying it.

## Contract

This workflow guarantees that the agent:

- validates the application context before touching anything;
- never sends a mutating request without first printing the resolved plan;
- keeps every generated artifact (SDK version, component files, clone) attributable to the app RID;
- documents capability gaps explicitly instead of guessing request bodies or UI flows.

It does not configure the third-party application itself; app registration,
scopes, and OAuth setup happen in the Foundry developer console UI.

## Variables

```bash
APP_RID="ri.foundry.third-party-application.main.application.abc123"
REPO_RID="ri.stemma.main.repository.abc123"        # code repository backing the app
WIDGET_SET_RID="ri.widgets.main.widget-set.abc123" # only when the app uses custom widgets
PROFILE="default"
```

## Phase 1: Validate the application context

Confirm the app exists and check its connection context (client/credentials
type, OAuth grants, redirect URLs, data scope). Read-only; no session is
established.

```bash
pltr dev-console connect "$APP_RID" --profile "$PROFILE"
```

Documented divergence: the vendor MCP's `connect_to_dev_console_app` is an
interactive IDE/workspace action with no headless equivalent, so this command
is its honest read-only form. Do not treat its output as an established
session.

## Phase 2: Inspect the OSDK definition

Read the generated OSDK definition to learn the package name, version, and the
object/action/query surface available to the app. Read-only.

```bash
# Latest version
pltr dev-console osdk definition "$APP_RID" --profile "$PROFILE"

# Pin a specific version and save it for reference
pltr dev-console osdk definition "$APP_RID" --version 1.2.0 \
  --format json --output osdk-definition.json
```

Optional ontology-side context when writing queries against the live ontology:

```bash
pltr osdk context --profile "$PROFILE"
pltr osdk examples --language typescript --profile "$PROFILE"
```

## Phase 3: Generate and install the SDK package

Mint a new OSDK version from the app's current `applicationVersion`. Dry-run
by default: without `--apply` the command prints the resolved version and the
exact request body and sends nothing mutating.

```bash
# 1. Print the dry-run plan (resolved version + exact POST body)
pltr dev-console sdk generate "$APP_RID" --profile "$PROFILE"

# 2. Mint the version for real (polls to a terminal status; ~24s observed)
pltr dev-console sdk generate "$APP_RID" --apply --profile "$PROFILE"
```

Generation changes a Foundry resource: run
[change-impact-assessment.md](change-impact-assessment.md) first when other
consumers depend on the app. Exit codes: `0` plan / requested / success, `1`
generation failed, `2` polling timeout (the version was still minted
server-side — do not blindly retry).

Install the generated package locally. Non-destructive by default: without
`--yes` or `--target` the command prints the resolved plan and changes
nothing.

```bash
# 1. Print the install plan
pltr dev-console sdk install "$APP_RID" --dry-run --profile "$PROFILE"

# 2a. Install into a project directory (npm --prefix / pip --target)
pltr dev-console sdk install "$APP_RID" --target ./my-app --profile "$PROFILE"

# 2b. Or install into the active Python virtualenv
pltr dev-console sdk install "$APP_RID" --yes --profile "$PROFILE"
```

## Phase 4: Scaffold typed React components

Local codegen, never network-mutating. Reads the app's data scope and the
ontology's object types, then writes one typed presentational
`<ApiName>Card.tsx` per in-scope object type plus an `index.ts` barrel.
`--output-dir` is required; existing files are never overwritten without
`--force`.

```bash
pltr dev-console convert-osdk-react "$APP_RID" \
  --output-dir ./my-app/src/components \
  --profile "$PROFILE"
```

Review the generated components before editing; regenerate with `--force` only
after confirming no hand edits would be lost.

## Phase 5: Clone the code repository

Inspect the repository that backs the app, then clone it for local
development.

```bash
# 1. Read repository context (metadata, default branch, refs, file tree)
pltr repository context "$REPO_RID" --profile "$PROFILE"

# 2. Print the clone plan without cloning
pltr repository clone "$REPO_RID" ./my-app --dry-run --profile "$PROFILE"

# 3. Clone for real
pltr repository clone "$REPO_RID" ./my-app --profile "$PROFILE"
```

The profile bearer token is passed via an environment-injected
`http.extraHeader` — never printed, never on the command line, never persisted
in the clone's config. Later `git fetch`/`git push` need fresh credentials.
The clone refuses to overwrite a non-empty target without `--force`.

## Phase 6: Consult the documentation corpus

Read the curated topic pages before writing app code; search for anything they
do not cover. All docs commands are read-only; search is bounded and honestly
partial.

```bash
pltr docs osdk-react-components
pltr docs custom-widgets          # when the app uses custom widgets
pltr docs search "osdk react useOsdkClient" --limit 10

# Load a specific page found via search as verbatim markdown
pltr docs page /foundry/custom-widgets/use-osdk/
```

## Phase 7: Widget dev mode and releases (custom widgets only)

Skip this phase when the app does not use custom widgets.

Enable widget dev mode for the current user so local widget code is served
into the app during development:

```bash
pltr widgets dev-mode enable --profile "$PROFILE"
```

Capability gap: only `enable` exists. There is no headless dev-mode disable
command; turn it off in the Foundry UI when development is done.

Inspect the widget set and its releases. Reads are plan-first by nature —
always list and get before deleting:

```bash
# Widget set details
pltr widgets get "$WIDGET_SET_RID" --profile "$PROFILE"

# Widget repository backing a code repository
pltr widgets repository get "$REPO_RID" --profile "$PROFILE"

# List releases, then inspect the one you intend to touch
pltr widgets release list "$WIDGET_SET_RID" --profile "$PROFILE"
pltr widgets release get "$WIDGET_SET_RID" 1.0.0 --profile "$PROFILE"
```

Delete a release only after inspecting it and running
[change-impact-assessment.md](change-impact-assessment.md) on the widget set;
`--yes` is required to skip the confirmation prompt:

```bash
pltr widgets release delete "$WIDGET_SET_RID" 1.0.0 --yes --profile "$PROFILE"
```

Capability gap: release creation is not exposed headlessly (only `list`,
`get`, `delete`). Cut new releases through the widget repository's CI or the
Foundry UI.

## Output Format

Report:

1. the app connection context observed in Phase 1 (credentials type, grants, scope);
2. the OSDK package name/version from the definition;
3. the SDK version minted (or the dry-run plan if not applied) and the install target;
4. generated component paths;
5. the local clone path and checked-out branch;
6. doc pages consulted;
7. widget dev-mode state and any release changes, with their change-impact artifacts.

## Anti-Patterns

- Running `sdk generate --apply` without first reading the dry-run plan
- Retrying `sdk generate` after exit code `2` without checking whether the version was already minted server-side
- Passing `--force` to `convert-osdk-react` or `repository clone` before confirming what would be overwritten
- Treating `dev-console connect` output as an authenticated session — it is a read-only validation
- Deleting a widget release without listing and inspecting it first
- Assuming headless commands exist for dev-mode disable or release creation — they do not; use the Foundry UI
- Committing credentials into the clone; later fetches must obtain fresh tokens
