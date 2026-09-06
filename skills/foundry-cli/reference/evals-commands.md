# Evals Commands (AIP Evals)

Evaluation suite and run operations, backed by the internal `foundry-evals`
Conjure service. All thirteen endpoint contracts were captured from the live
AIP Evals UI on a live Foundry deployment via Chrome DevTools Protocol
on 2026-09-04; every listed call returned HTTP 200 (capture artifact:
`/tmp/evals-capture/capture.jsonl`).

Suite RIDs look like `ri.evals..evaluation-suite.<uuid>` — note the DOUBLE
DOT (empty service segment), which is server-evidenced.

Known gap: the suite config-WRITE endpoint was never observed — the UI
appears to embed run-scoped config in the `/run` body. Suite-level config
write is deliberately not implemented.

## Suite Commands

### List Evaluation Suites for a Target

```bash
pfoundry evals suite list --target FUNCTION_RID [--format FORMAT]

# Backed by PUT /foundry-evals/api/evals/config/v2/target/get-evaluation-suites
# with body {"linkedTarget": {"function": rid, "type": "function"}}. Only the
# function target arm was captured; other target kinds are not guessed.
# Returns {"evaluationSuiteRids": [...]}.

# Example
pfoundry evals suite list --target ri.function-registry.main.function.00000000-0000-0000-0000-000000000007
```

### Get Evaluation Suite Config

```bash
pfoundry evals suite get SUITE_RID [--version VERSION] [--legacy] [--format FORMAT]

# Default: v2 config — PUT /foundry-evals/api/evals/config/v2/get with body
# {"requests": [{"rid": SUITE_RID}]} (metrics, test case definitions,
# execution backend). --version pins the read via the version endpoints
# (PUT .../config/v2/version/get); --legacy switches to the pre-metrics
# endpoints (PUT .../config/get with {"rids": [rid]} and
# PUT .../config/version/get). All four variants were captured with HTTP 200.

# Example
pfoundry evals suite get ri.evals..evaluation-suite.00000000-0000-0000-0000-000000000002
```

### List Evaluators

```bash
pfoundry evals suite evaluators [--format FORMAT]

# PUT /foundry-evals/api/evals/config/evaluators/get, empty body. Returns
# the evaluator catalog ({"evaluators": [...]}); no suite scoping was
# observed in the capture.
```

### List Auto-Generated Metrics

```bash
pfoundry evals suite auto-metrics [--format FORMAT]

# PUT /foundry-evals/api/evals/config/auto-generated-metric/get, empty body.
# Returns {"metrics": [...]} (token counts, compute cost, duration, ...).
```

### Suggested Execution Scope

```bash
pfoundry evals suite suggested-scope SUITE_RID --execution-target FILE [--format FORMAT]

# PUT /foundry-evals/api/evals/execute/v3/{suiteRid}/suggestedExecutionScope
# with body {"executionTargets": [target], "extraResources": []}. FILE is a
# JSON document with one ExecutionTarget object ('-' reads stdin) — the same
# shape as the run body's executionTarget.

# Example
pfoundry evals suite suggested-scope ri.evals..evaluation-suite.00000000-0000-0000-0000-000000000002 \
    --execution-target execution-target.json
```

## Run Commands

### List Run History

```bash
pfoundry evals run list SUITE_RID [--page-size N] [--format FORMAT]

# PUT /foundry-evals/api/evals/execute/v3/{suiteRid}/history with body
# {"executionTarget": null, "pageSize": N}. Returns {"executionsPage": [...]}
# with execution metadata and aggregated metrics per run.

# Example
pfoundry evals run list ri.evals..evaluation-suite.00000000-0000-0000-0000-000000000002 --page-size 20
```

### Run Summary

```bash
pfoundry evals run summary SUITE_RID EXECUTION_ID [--format FORMAT]

# PUT /foundry-evals/api/evals/execute/execution/{suiteRid}/summary with
# body {"executionId": ...}. Returns {"summary": {...}} — aggregated metric
# scores and test case counts for one run.

# Example
pfoundry evals run summary ri.evals..evaluation-suite.00000000-0000-0000-0000-000000000002 \
    00000000-0000-0000-0000-000000000008
```

### Run Test Cases

```bash
pfoundry evals run test-cases SUITE_RID EXECUTION_ID [--page-size N] [--v3] [--format FORMAT]

# Default: PUT /foundry-evals/api/evals/execute/execution/{suiteRid}/testCases;
# --v3 switches to PUT /foundry-evals/api/evals/execute/v3/execution/{suiteRid}/testCases.
# Both take {"executionId", "pageSize"} and return {"testCaseResults": [...]};
# the per-result shapes differ between the two variants (both captured).

# Example
pfoundry evals run test-cases ri.evals..evaluation-suite.00000000-0000-0000-0000-000000000002 \
    00000000-0000-0000-0000-000000000008 --v3
```

### Trigger a Run (plan-first; --apply issues the real run)

```bash
pfoundry evals run trigger SUITE_RID --definition FILE [--apply] [--format FORMAT]

# PUT /foundry-evals/api/evals/execute/v3/{suiteRid}/run. FILE is a JSON
# document ('-' reads stdin) with the run body:
#   {"executionTarget": {...}, "backendParameters": {...}, "reportMetadata": {...}}
# sent verbatim. Success response: {"buildRid", "jobRid", "executionId"}.
#
# Without --apply the command issues NO mutation: it prints the resolved run
# body plus the read-only suggestedExecutionScope for the body's
# executionTarget. With --apply it triggers the run and prints the returned
# build/job/execution identifiers.

# Example (dry-run plan)
pfoundry evals run trigger ri.evals..evaluation-suite.00000000-0000-0000-0000-000000000002 \
    --definition run.json

# Example (real run)
pfoundry evals run trigger ri.evals..evaluation-suite.00000000-0000-0000-0000-000000000002 \
    --definition run.json --apply
```
