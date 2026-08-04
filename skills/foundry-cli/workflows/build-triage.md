# Build Triage Workflow

Use this workflow to diagnose a failed or stuck Foundry build and decide on remediation. Phases 1-6 are read-only. Phase 7 mutates Foundry resources and is plan-first: present the exact command and obtain explicit operator confirmation before executing it.

## Contract

This workflow guarantees that the agent:

- locates the failing build and identifies the exact failing or stuck jobs;
- gathers evidence from job metadata, compute-module logs, data-health reports, and output-dataset spot-checks before proposing a cause;
- separates observed evidence from inference and preserves coverage gaps;
- proposes remediation (rerun build, cancel build, pause schedule) only after the evidence phases complete;
- executes remediation mutations only after presenting the exact command and receiving explicit operator confirmation;
- verifies the outcome after remediation.

It does not diagnose transforms code, Spark plans, or non-compute-module job internals; those gaps are reported, not guessed.

## Capability Gaps

State these before triage begins; do not work around them silently:

- There is no dedicated `builds rerun` command. A rerun is `foundry orchestration builds create` with the same target JSON.
- `orchestration builds create`, `orchestration builds cancel`, `orchestration schedules pause`, and `orchestration schedules unpause` have no `--apply`, `--yes`, or dry-run flag. They mutate immediately. Plan-first is enforced by this workflow, not by the CLI.
- `foundry compute logs` covers compute-module jobs only. There is no log command for Spark or other job types; document that as a gap when the failing job is not a compute-module job.
- `foundry data-health report get` requires both a check RID and a report RID. There is no command to list reports for a check; if report RIDs are not visible in the check details, report the gap.
- The `compute logs` step-2 response shape is bundle-derived and not contract-verified; treat its payload as raw evidence, not parsed truth.

## Phase 1: Locate the build

If the build RID is given, skip to Phase 2. Otherwise search recent builds:

```bash
foundry orchestration builds search --profile "$PROFILE" --format json --output builds.json
```

Use `--page-size`, `--max-pages`, or `--all` when the first page does not reach the failure window. Filter `builds.json` locally (status, branch, creation time) to select the candidate `ri.orchestration.main.build.*` RID. Do not page the full build history into agent context.

## Phase 2: Read the build

```bash
foundry orchestration builds get ri.orchestration.main.build.abc123 \
  --profile "$PROFILE" --format json --output build.json
```

Record status, branch, target, created-by, and any schedule association. A `RUNNING` build with no recent job progress is the stuck case; a `FAILED` build proceeds directly to job isolation.

## Phase 3: Isolate the failing jobs

```bash
foundry orchestration builds jobs ri.orchestration.main.build.abc123 \
  --profile "$PROFILE" --format json --output jobs.json
```

Extract failed or long-running job RIDs locally:

```bash
JOB_RIDS=$(jq -r '.[] | select(.status == "FAILED" or .status == "RUNNING") | .rid' jobs.json | tr '\n' ',' | sed 's/,$//')
foundry orchestration jobs get-batch "$JOB_RIDS" --profile "$PROFILE" --format json --output job-details.json
```

Use `foundry orchestration jobs get ri.orchestration.main.job.def456 --format json` for a single job. `get-batch` accepts a comma-separated list, max 500. Record each failing job's type, status, duration, and output dataset RID.

## Phase 4: Pull logs for compute-module jobs

For each failing job whose type is a compute module:

```bash
foundry compute logs ri.orchestration.main.job.def456 \
  --profile "$PROFILE" --page-size-limit 500 --reverse \
  --format json --output job-logs.json
```

`--reverse` returns newest-first, which surfaces the failure tail first. Widen the window with `--from-inclusive` / `--to-exclusive` (microseconds since epoch) when the default 24-hour range misses the failure. Treat the payload as raw: the read shape is not contract-verified. For non-compute-module jobs, record the no-logs gap and continue.

## Phase 5: Check data-health reports

When the failure looks like a quality gate rather than a crash, inspect the checks on the output dataset:

```bash
foundry data-health check get ri.data-health.main.check.abc123 \
  --profile "$PROFILE" --format json

foundry data-health report get ri.data-health.main.check.abc123 \
  ri.data-health.main.check-report.def456 \
  --profile "$PROFILE" --format json --output report.json
```

Report statuses are `PASSED`, `FAILED`, `WARNING`, `ERROR`, `NOT_APPLICABLE`, `NOT_COMPUTABLE`. A `FAILED` or `ERROR` report on a quality gate is evidence for bad input data or a contract drift, not a compute fault. If report RIDs cannot be obtained, state the gap rather than assuming checks passed.

## Phase 6: Spot-check the output dataset

Query the output dataset directly to distinguish "build failed, no output" from "build succeeded, output is wrong". SQL is preview-mode by default; keep queries small:

```bash
foundry sql execute "SELECT COUNT(*) AS row_count FROM my_output_dataset" \
  --profile "$PROFILE"

foundry sql execute "SELECT * FROM my_output_dataset LIMIT 10" \
  --profile "$PROFILE" --format json --output sample.json

foundry sql execute "SELECT MAX(updated_at) AS latest FROM my_output_dataset" \
  --profile "$PROFILE"
```

Use `foundry sql submit` + `foundry sql wait` for heavier checks. Zero rows after a "successful" build, stale `MAX` timestamps, or nulls in required columns all point remediation at the pipeline logic, not at a retry.

## Phase 7: Decide and gate remediation

Choose one remediation and present it plan-first:

1. State the diagnosed cause and the evidence (job RID, log excerpt, report status, SQL result).
2. State the exact command to run.
3. Wait for explicit operator confirmation. The orchestration mutation commands have no built-in dry-run or confirmation flag; the operator's confirmation is the only gate.
4. If the remediation changes what a Foundry resource produces (for example pausing a production schedule whose outputs have downstream consumers), run workflows/change-impact-assessment.md on the affected resource before executing.

Remediation options:

```bash
# Rerun: create a new build for the same target (there is no rerun command)
foundry orchestration builds create \
  '{"type": "manual", "targetRids": ["ri.foundry.main.dataset.abc123"]}' \
  --branch master --force

# Cancel a stuck build and its unfinished jobs
foundry orchestration builds cancel ri.orchestration.main.build.abc123

# Pause the schedule while the root cause is fixed
foundry orchestration schedules pause ri.orchestration.main.schedule.ghi789

# Resume after the fix is verified
foundry orchestration schedules unpause ri.orchestration.main.schedule.ghi789
```

Decision rules:

- Transient fault (infrastructure error in logs, no data-quality evidence): rerun the build.
- Stuck build blocking a schedule: cancel the build, then rerun.
- Bad input data or failing quality gate: do not rerun blindly; pause the schedule if it will keep firing, fix the upstream cause, then rerun.
- Code or contract defect: no CLI remediation; escalate to the owning repository. Say so.

## Phase 8: Verify the outcome

After a rerun, poll the new build; after an unpause, confirm the schedule fires:

```bash
foundry orchestration builds get ri.orchestration.main.build.new456 \
  --profile "$PROFILE" --format json

foundry orchestration schedules runs ri.orchestration.main.schedule.ghi789 \
  --profile "$PROFILE" --page-size 5 --format json
```

Re-run the Phase 6 spot-checks against the fresh output. Remediation is complete only when the new build succeeds and the spot-checks pass.

## Output Format

Report:

1. build RID, status, branch, and schedule association;
2. failing or stuck jobs with type, status, and duration;
3. log evidence for compute-module jobs, or the explicit no-logs gap;
4. data-health report statuses, or the explicit no-report-RIDs gap;
5. SQL spot-check results on the output dataset;
6. diagnosed cause, labeled as observed evidence vs inference;
7. remediation taken, the operator confirmation received, and any change-impact assessment run;
8. post-remediation verification result.

## Anti-Patterns

- Rerunning a build before isolating which job failed and why
- Treating a missing log or missing health report as "no problem found"
- Executing `builds create`, `builds cancel`, or `schedules pause` without presenting the exact command and obtaining operator confirmation first
- Inventing a dry-run flag for orchestration mutations; none exists
- Assuming a failed quality gate means retry; it usually means bad input or contract drift
- Pulling full build history or full job logs into agent context instead of filtering locally with `jq`
- Claiming remediation succeeded without re-checking the new build and the output dataset
