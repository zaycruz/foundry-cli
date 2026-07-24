# Repository Commands

Read-only code repository pull-request inspection, backed by the internal
`stemma-pull-request` API.

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
