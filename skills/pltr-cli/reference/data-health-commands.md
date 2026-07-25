# Data Health Commands

Manage data health checks and read their execution reports.

## Check Commands

### Create Check

```bash
pltr data-health check create CONFIG [--intent TEXT] [--format FORMAT]

# CONFIG is a JSON string or @filepath and must include a 'type' field.
# Supported check types include buildStatus, buildDuration, nullPercentage,
# columnType, numericColumnRange, and more.

# Examples
pltr data-health check create '{
    "type": "buildStatus",
    "subject": {
        "datasetRid": "ri.foundry.main.dataset.xxx",
        "branchId": "master"
    },
    "statusCheckConfig": {"severity": "WARNING"}
}' --intent "Monitor production builds"

pltr data-health check create @check-config.json
```

### Get Check

```bash
pltr data-health check get CHECK_RID [--format FORMAT]

# Example
pltr data-health check get ri.data-health.main.check.abc123
```

### Replace Check

```bash
pltr data-health check replace CHECK_RID CONFIG [--intent TEXT] [--format FORMAT]

# CONFIG is a JSON string or @filepath. Changing the type of a check after
# creation is not supported.

# Example
pltr data-health check replace ri.data-health.main.check.abc123 @updated-config.json
```

### Delete Check

```bash
pltr data-health check delete CHECK_RID [--force]

# Example
pltr data-health check delete ri.data-health.main.check.abc123 --force
```

## Report Commands

### Get Check Report

```bash
pltr data-health report get CHECK_RID CHECK_REPORT_RID [--format FORMAT]

# Result statuses: PASSED, FAILED, WARNING, ERROR, NOT_APPLICABLE,
# NOT_COMPUTABLE

# Example
pltr data-health report get ri.data-health.main.check.abc123 \
    ri.data-health.main.check-report.def456 --format json
```
