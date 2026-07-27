# Compute Module Operations Workflow

Use this workflow to operate a Foundry Compute Module: inspect status and config, read logs for one build job RID, manage dev mode, and execute a function on a running FUNCTION-mode module. Read-only phases come first; every mutation is plan-first and gated.

## Contract

This workflow guarantees that the agent:

- pulls the real compute-module documentation before authoring or invoking a function;
- establishes module mode, branch, and running state from observed status before any execution;
- keeps the unverified-shape status of every response visible instead of assuming a contract;
- presents every mutation as a dry-run plan first and requires the explicit apply/confirmation flags;
- runs a change-impact assessment before a dev-mode change that affects shared consumers.

It does not create, deploy, or upgrade a compute module. `pltr compute` has no list or discovery command; the deployed-app RID must come from an external source (ticket, config, Compass). Do not invent one.

## Phase 1: Pull the real compute docs

Before authoring or invoking any function, read the curated compute-module documentation page:

```bash
pltr docs compute
```

For follow-up pages from the wider corpus, use the bounded search and verbatim page loader:

```bash
pltr docs search "compute module functions" --limit 5
pltr docs page /docs/foundry/compute-modules/overview
```

Do not rely on memory for function query types, input shapes, or module modes. The docs are the source of truth; search is bounded and honestly partial, so treat a missed hit as "not found," not "does not exist."

## Phase 2: Inspect status and config (read-only)

Load both status and config for the module, pinning the branch explicitly:

```bash
pltr compute info ri.foundry.main.deployed-app.abc123 \
  --branch "$BRANCH" \
  --profile "$PROFILE" \
  --format json \
  --output ./compute-info.json
```

Use `--include status` or `--include config` (repeatable) when only one side is needed:

```bash
pltr compute info ri.foundry.main.deployed-app.abc123 --include status --branch "$BRANCH"
```

Required interpretation:

1. Record the branch actually queried; the default is `master` and may not be the branch under test.
2. Confirm the module is FUNCTION-mode before planning a `compute execute`; execution only works on FUNCTION-mode modules that are running.
3. Confirm the module is running before planning an execution.
4. Treat success shapes as UNVERIFIED. The contour/build2 endpoints are contract-verified only via their error contracts (403 `Contour:InsufficientPermission` proves the mount); success payloads are passed through raw with `shape_verified: false` in the agent envelope. Do not build downstream logic on fields whose presence has not been observed.
5. Carry the deployed-app RID and any build/job RID reported in status into later phases. If status does not surface a job RID, that is a discovery gap — report it rather than guessing one.

## Phase 3: Read logs for one build job RID (read-only)

`pltr compute logs` takes a build job (run) RID, not the deployed-app RID:

```bash
pltr compute logs ri.foundry.main.job.abc123 \
  --page-size-limit 500 \
  --profile "$PROFILE" \
  --format json \
  --output ./compute-logs.json
```

Bound the window with microsecond-since-epoch timestamps when the default last-24-hours range is wrong:

```bash
FROM_MICROS="$(( $(date +%s) - 7200 ))000000"
pltr compute logs ri.foundry.main.job.abc123 \
  --from-inclusive "$FROM_MICROS" \
  --page-size-limit 1000 \
  --reverse
```

Rules:

- Default is the last 24 hours, chronological, 100 entries (max 1000). Raise `--page-size-limit` before concluding a log line is absent.
- Use `--reverse` (newest-first) when triaging a recent failure.
- Step 2 of the telemetry flow (`logs/read/v3`) is bundle-derived and NOT contract-verified; the response is passed through raw. Treat its shape as unverified, same as Phase 2.
- An empty window is a bounded result, not proof the job produced no logs. Widen the window or verify the job RID before reporting absence.

## Phase 4: Manage dev mode (plan-first)

Dev mode disables automatic upgrades until an ISO-8601 deadline (max +5h). This changes module behavior for every consumer of the module.

Gate: if the module serves shared pipelines or applications, run `workflows/change-impact-assessment.md` on the surrounding resolvable resource first and carry its baseline artifact into the review record.

Step 1 — print the dry-run plan (no network request is issued):

```bash
pltr compute manage --action dev-mode \
  --deployed-app-rid ri.foundry.main.deployed-app.abc123 \
  --branch "$BRANCH" \
  --dev-mode-until 2026-07-27T23:00:00Z \
  --profile "$PROFILE"
```

Step 2 — review the plan, then apply explicitly:

```bash
pltr compute manage --action dev-mode \
  --deployed-app-rid ri.foundry.main.deployed-app.abc123 \
  --branch "$BRANCH" \
  --dev-mode-until 2026-07-27T23:00:00Z \
  --profile "$PROFILE" \
  --apply
```

To disable dev mode, omit `--dev-mode-until` (an empty body is sent):

```bash
pltr compute manage --action dev-mode \
  --deployed-app-rid ri.foundry.main.deployed-app.abc123 \
  --branch "$BRANCH" \
  --profile "$PROFILE" \
  --apply
```

`manage` also covers `start` (`--deployed-app-rid`) and `stop` (`--build-rid`); both are plan-first, and `stop` additionally requires `--yes` with `--apply`. Keep them out of this workflow unless the operating task actually calls for a lifecycle change; stopping a module cancels a build and is the highest-blast-radius action here.

## Phase 5: Execute a function (plan-first)

Prerequisites from earlier phases: docs read (Phase 1), FUNCTION-mode confirmed, module running (Phase 2).

Step 1 — print the dry-run plan (no network request is issued):

```bash
pltr compute execute ri.foundry.main.deployed-app.abc123 \
  --query-type my-function \
  --query '{"input": 1}' \
  --branch "$BRANCH" \
  --profile "$PROFILE"
```

Step 2 — review the plan against the documented function signature, then apply explicitly:

```bash
pltr compute execute ri.foundry.main.deployed-app.abc123 \
  --query-type my-function \
  --query '{"input": 1}' \
  --branch "$BRANCH" \
  --profile "$PROFILE" \
  --apply \
  --format json \
  --output ./compute-execute-result.json
```

Rules:

- `--query-type` and `--query` must come from the documentation read in Phase 1, not from inference. If the docs do not cover the function, stop and report the gap.
- The response is a raw octet-stream (the function's return value, expected JSON). Its shape is UNVERIFIED and passed through raw; save it with `--output` before parsing.
- A failed execution still issues a real job. Retry only after reading the module's logs (Phase 3) with the job RID from the failure.

## Output Format

Report:

1. docs consulted (page paths), and any function signature gap;
2. deployed-app RID, branch, module mode, and running state as observed;
3. config facts relied upon, each marked verified or unverified (`shape_verified`);
4. log window queried, entry count, and relevant lines for the job RID;
5. every dry-run plan shown, and whether `--apply` / `--yes` was issued;
6. execution result artifact path, or the raw error and the job RID used for log follow-up;
7. coverage gaps: anything not observable through the verified surface (e.g., no module discovery, unverified success shapes).

## Anti-Patterns

- Invoking a function without pulling `pltr docs compute` first
- Assuming a query type or input shape that the docs do not show
- Running `compute execute` before confirming FUNCTION-mode and running state
- Passing a deployed-app RID to `compute logs` (it requires a build job RID)
- Adding `--apply` without first printing and reviewing the dry-run plan
- Applying a dev-mode change to a shared module without a change-impact assessment
- Omitting `--branch` and silently operating on `master`
- Treating unverified success shapes (`shape_verified: false`) as a stable contract
- Concluding "no logs" from the default 100-entry, 24-hour window
- Guessing a deployed-app RID instead of reporting the no-discovery gap
