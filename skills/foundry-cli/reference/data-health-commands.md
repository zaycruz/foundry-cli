# Data Health Commands

Manage data health checks and read their execution reports.

## Check Commands

### Create Check

```bash
pfoundry data-health check create CONFIG [--intent TEXT] [--format FORMAT]

# CONFIG is a JSON string or @filepath and must include a 'type' field.
# Supported check types include buildStatus, buildDuration, nullPercentage,
# columnType, numericColumnRange, and more.

# Examples
pfoundry data-health check create '{
    "type": "buildStatus",
    "subject": {
        "datasetRid": "ri.foundry.main.dataset.xxx",
        "branchId": "master"
    },
    "statusCheckConfig": {"severity": "WARNING"}
}' --intent "Monitor production builds"

pfoundry data-health check create @check-config.json
```

### Get Check

```bash
pfoundry data-health check get CHECK_RID [--format FORMAT]

# Example
pfoundry data-health check get ri.data-health.main.check.abc123
```

### Replace Check

```bash
pfoundry data-health check replace CHECK_RID CONFIG [--intent TEXT] [--format FORMAT]

# CONFIG is a JSON string or @filepath. Changing the type of a check after
# creation is not supported.

# Example
pfoundry data-health check replace ri.data-health.main.check.abc123 @updated-config.json
```

### Delete Check

```bash
pfoundry data-health check delete CHECK_RID [--force]

# Example
pfoundry data-health check delete ri.data-health.main.check.abc123 --force
```

## Report Commands

### Get Check Report

```bash
pfoundry data-health report get CHECK_RID CHECK_REPORT_RID [--format FORMAT]

# Result statuses: PASSED, FAILED, WARNING, ERROR, NOT_APPLICABLE,
# NOT_COMPUTABLE

# Example
pfoundry data-health report get ri.data-health.main.check.abc123 \
    ri.data-health.main.check-report.def456 --format json
```
