# Repository Commands

Code repository pull-request inspection and contract-verified pull-request
writes, backed by the internal `stemma-pull-request` API. Also covers
headless repository context reads and git clones via the internal `stemma`
API, plus Python transforms repository creation (dry-run plan by default,
real creation behind `--apply`).

## Repository Inspection

### Repository Context (read-only)

```bash
pfoundry repository context REPOSITORY_RID [--path PREFIX] [--ref REF] [--no-tree] [--format FORMAT]

# Aggregates the contract-verified internal stemma reads: repository metadata
# (stemma + Compass name/path), the default branch (HEAD), branch and tag
# refs, and the recursive file tree at a ref.

# Example
pfoundry repository context ri.stemma.main.repository.abc123
```

### Clone Repository

```bash
pfoundry repository clone REPOSITORY_RID TARGET_DIR [--branch BRANCH] [--force] [--dry-run]

# Resolves the git URL from the contract-verified stemma smart-HTTP endpoint
# (https://<host>/stemma/git/<repositoryRid>) and runs `git clone` with the
# profile bearer token passed via an environment-injected http.extraHeader
# -- the token is never printed, never on the command line, and never
# persisted in the clone's config (later fetches need fresh credentials).
# Refuses to overwrite a non-empty target without --force.

# Example
pfoundry repository clone ri.stemma.main.repository.abc123 ./my-repo
```

### Push One Branch (dry-run default; --apply required)

```bash
pfoundry repository push REPOSITORY_RID refs/heads/LOCAL_BRANCH refs/heads/DESTINATION_BRANCH [--apply]
```

The command reads and verifies repository context first, then requires the
local `origin` URL to equal either the profile-host smart-HTTP URL
`https://<host>/stemma/git/<repositoryRid>` or that URL plus the exact
repository-name suffix returned by live context. Both refs must be fully qualified
`refs/heads/*` refs. The default branch, tags, deletes, force syntax/options,
arbitrary refspecs, missing or ambiguous local refs, mismatched profile hosts,
repository RIDs, or remotes are rejected.

The exact destination ref is read before the write. If it exists, it must be an
ancestor of the local commit. With `--apply`, exactly one non-force refspec is
sent, then the destination is read back and must equal the local commit. The
bearer token is injected only through temporary `GIT_CONFIG_*` environment
variables; it is never placed in argv, persisted in repository config, output,
or errors. Without `--apply`, no push is issued.

```bash
pfoundry repository push ri.stemma.main.repository.abc123 \
    refs/heads/feature refs/heads/review
pfoundry repository push ri.stemma.main.repository.abc123 \
    refs/heads/feature refs/heads/review --apply
```

## Repository Creation

### Create Python Transforms Repository (dry-run default; --apply creates)

```bash
pfoundry repository create-python-transforms NAME --parent-rid FOLDER_RID [--apply]

# Uses the two-call chain derived from the published client contract
#  against a live deployment (the captured contract
# the captured contract), verified live against a live deployment the same day
# (the captured contract):
#   1. Read-only preflight: FOLDER_RID -> enclosing project -> full Compass
#      path via the compass hierarchy batch endpoints. The repository
#      always lands in the project ROOT.
#   2. POST /stemma/api/repos {"path": "<projectPath>/<name>"} -> {rid}.
#   3. POST /repository-bootstrapper/api/repos/<rid>/bootstrap applies the
#      Python transforms template (master branch + 0.0.1 tag), then the
#      refs are read back for verification.
# Without --apply only the read-only preflight runs and the exact intended
# writes are printed as a dry-run plan; --parent-rid is required.
# Cleanup: foundry resource delete RID --force (trash) + foundry resource
# permanently-delete RID --force.

# Examples
pfoundry repository create-python-transforms my-transforms --parent-rid ri.compass.main.folder.abc123
pfoundry repository create-python-transforms my-transforms --parent-rid ri.compass.main.folder.abc123 --apply
```

## Pull Request Commands

### List Pull Requests

```bash
pfoundry repository pull-request list [REPOSITORY_RID] [--format FORMAT]

# REPOSITORY_RID filters client-side; the internal list endpoint enumerates
# pull requests across repositories

# Examples
pfoundry repository pull-request list
pfoundry repository pull-request list ri.stemma.main.repository.abc123
```

### Get Pull Request

```bash
pfoundry repository pull-request get PULL_REQUEST_RID [--format FORMAT]

# Example
pfoundry repository pull-request get ri.pull-request.main.pull-request.abc123
```

### Create Pull Request

```bash
pfoundry repository pull-request create TITLE \
    --base-repository-rid REPOSITORY_RID \
    --head-commitish refs/heads/BRANCH \
    [--head-repository-rid REPOSITORY_RID] [--base-branch refs/heads/master] \
    [--description TEXT] [--apply] [--format FORMAT]

# Default is a dry-run plan of the exact verified POST body; nothing is
# written without --apply (contract verified against a live deployment, see
# the captured contract)

# Examples
pfoundry repository pull-request create "feat: add x" \
    --base-repository-rid ri.stemma.main.repository.abc123 \
    --head-commitish refs/heads/feat/x
pfoundry repository pull-request create "feat: add x" \
    --base-repository-rid ri.stemma.main.repository.abc123 \
    --head-commitish refs/heads/feat/x --apply
```

### Comment on Pull Request

```bash
pfoundry repository pull-request comment PULL_REQUEST_RID CONTENT [--apply] [--format FORMAT]

# Posts a global comment; default is a dry-run plan, nothing is written
# without --apply

# Example
pfoundry repository pull-request comment ri.pull-request.main.pull-request.abc123 \
    "looks good" --apply
```

### Close Pull Request

```bash
pfoundry repository pull-request close PULL_REQUEST_RID [--apply] [--yes] [--format FORMAT]

# Closes the pull request via PUT /pulls/{rid}/update with
# {"title": <current title>, "status": "CLOSED"} (both fields required;
# contract verified against a live deployment, see
# the captured contract). The pull request is read first to
# obtain its title. Default is a dry-run plan of the exact PUT body; the
# real close requires --apply --yes. An already-CLOSED pull request is
# reported as already-closed instead of being re-closed.

# Examples
pfoundry repository pull-request close ri.pull-request.main.pull-request.abc123
pfoundry repository pull-request close ri.pull-request.main.pull-request.abc123 \
    --apply --yes
```
