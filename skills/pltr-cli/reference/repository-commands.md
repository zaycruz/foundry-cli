# Repository Commands

Code repository pull-request inspection and contract-verified pull-request
writes, backed by the internal `stemma-pull-request` API. Also covers
headless repository context reads and git clones via the internal `stemma`
API, plus a plan-only repository creation command.

## Repository Inspection

### Repository Context (read-only)

```bash
pltr repository context REPOSITORY_RID [--path PREFIX] [--ref REF] [--no-tree] [--format FORMAT]

# Aggregates the contract-verified internal stemma reads: repository metadata
# (stemma + Compass name/path), the default branch (HEAD), branch and tag
# refs, and the recursive file tree at a ref.

# Example
pltr repository context ri.stemma.main.repository.abc123
```

### Clone Repository

```bash
pltr repository clone REPOSITORY_RID TARGET_DIR [--branch BRANCH] [--force] [--dry-run]

# Resolves the git URL from the contract-verified stemma smart-HTTP endpoint
# (https://<host>/stemma/git/<repositoryRid>) and runs `git clone` with the
# profile bearer token passed via an environment-injected http.extraHeader
# -- the token is never printed, never on the command line, and never
# persisted in the clone's config (later fetches need fresh credentials).
# Refuses to overwrite a non-empty target without --force.

# Example
pltr repository clone ri.stemma.main.repository.abc123 ./my-repo
```

## Repository Creation

### Create Python Transforms Repository (plan-only; --apply blocked)

```bash
pltr repository create-python-transforms NAME [--parent-rid FOLDER_RID] [--apply]

# Deliberate no-mutation posture: the stemma createRepository endpoint is
# catalogue-only and its request contract could not be verified on the a live Foundry deployment
# stack (12 candidate bodies all returned opaque 500s; see
# the captured contract*.jsonl). The CLI prints the intended write
# as a dry-run plan and refuses to guess: --apply fails loudly with the
# verification evidence instead of issuing a speculative mutation.

# Example
pltr repository create-python-transforms my-transforms --parent-rid ri.compass.main.folder.abc123
```

## Pull Request Commands

### List Pull Requests

```bash
pltr repository pull-request list [REPOSITORY_RID] [--format FORMAT]

# REPOSITORY_RID filters client-side; the internal list endpoint enumerates
# pull requests across repositories

# Examples
pltr repository pull-request list
pltr repository pull-request list ri.stemma.main.repository.abc123
```

### Get Pull Request

```bash
pltr repository pull-request get PULL_REQUEST_RID [--format FORMAT]

# Example
pltr repository pull-request get ri.pull-request.main.pull-request.abc123
```

### Create Pull Request

```bash
pltr repository pull-request create TITLE \
    --base-repository-rid REPOSITORY_RID \
    --head-commitish refs/heads/BRANCH \
    [--head-repository-rid REPOSITORY_RID] [--base-branch refs/heads/master] \
    [--description TEXT] [--apply] [--format FORMAT]

# Default is a dry-run plan of the exact verified POST body; nothing is
# written without --apply (contract contract-verified on a live Foundry deployment, see
# the captured contract)

# Examples
pltr repository pull-request create "feat: add x" \
    --base-repository-rid ri.stemma.main.repository.abc123 \
    --head-commitish refs/heads/feat/x
pltr repository pull-request create "feat: add x" \
    --base-repository-rid ri.stemma.main.repository.abc123 \
    --head-commitish refs/heads/feat/x --apply
```

### Comment on Pull Request

```bash
pltr repository pull-request comment PULL_REQUEST_RID CONTENT [--apply] [--format FORMAT]

# Posts a global comment; default is a dry-run plan, nothing is written
# without --apply

# Example
pltr repository pull-request comment ri.pull-request.main.pull-request.abc123 \
    "looks good" --apply
```
