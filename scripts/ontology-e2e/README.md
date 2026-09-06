# Ontology E2E workflow suite

Real-stack ontology lifecycle tests. These workflows MUTATE a real Foundry
stack, so they are not part of push/PR CI. They create disposable resources
and clean them up on exit.

## Workflows

- `.github/workflows/ontology-e2e.yml` — runs `scripts/ontology-e2e/run-lifecycle.sh`
  against the stack configured in GitHub secrets. Manual trigger
  (`workflow_dispatch`) or nightly schedule.

## What the lifecycle exercises

1. Create a disposable project in a space.
2. Create a backing dataset inside the project.
3. Set the backing dataset schema (publication order step 1).
4. Object-type upsert with `--apply` (publication order step 3).
5. Object-type read-back.
6. Object-type add-property (dry-run then apply).
7. Link-type upsert dry-run.
8. Guarded upsert dry-run (needs-verification expected on existing types).
9. Object-type list / count.
10. Object-type delete with `--apply --yes`.
11. Cleanup: delete object type, trash the project.

## Requirements

- GitHub repository secrets:
  - `FOUNDRY_HOST` — stack hostname (e.g. `your-stack.palantirfoundry.com`)
  - `FOUNDRY_TOKEN` — API token with ontology + filesystem write access
  - `ONTOLOGY_RID` — the ontology to run against
  - `SPACE_RID` (optional) — space for the disposable project
- The workflow uses the `foundry-test` environment; configure it under
  Settings → Environments.

## Stack prerequisites

The stack must provision dataset views for newly created datasets. Sandboxes
often do NOT (they return `DatasetViewNotFound` on schema set); the script
detects this and exits 2 with a clear message. Run against a real test stack
with dataset views enabled.

## Run locally

```bash
export FOUNDRY_HOST="https://your-stack.palantirfoundry.com"
export FOUNDRY_TOKEN="your-token"
export ONTOLOGY_RID="ri.ontology.main.ontology.<uuid>"
export SPACE_RID="ri.compass.main.folder.<uuid>"   # optional
export PFOUNDRY="$(which pfoundry)"                 # optional
bash scripts/ontology-e2e/run-lifecycle.sh
```

Exit codes: `0` full lifecycle passed, `1` a step failed, `2` stack
limitation (dataset views not provisioned).
