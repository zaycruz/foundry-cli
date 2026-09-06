# Admin Commands

User, group, role, and organization management. **Requires admin permissions**.

## User Commands

### List Users

```bash
pfoundry admin user list [--page-size N] [--page-token TEXT] [--format FORMAT]

# Example
pfoundry admin user list --page-size 50 --format csv --output users.csv
```

### Get User Info

```bash
pfoundry admin user get USER_ID [--format FORMAT]

# Example
pfoundry admin user get john.doe@company.com
```

### Current User

```bash
pfoundry admin user current [--format FORMAT]

# Example
pfoundry admin user current --format json
```

### Search Users

```bash
pfoundry admin user search QUERY [--page-size N] [--format FORMAT]

# Example
pfoundry admin user search "john" --page-size 20
```

### Get User Markings/Permissions

```bash
pfoundry admin user markings USER_ID [--format FORMAT]

# Example
pfoundry admin user markings john.doe@company.com
```

### Revoke User Tokens

```bash
pfoundry admin user revoke-tokens USER_ID [--confirm]

# Example
pfoundry admin user revoke-tokens john.doe@company.com --confirm
```

### Delete User

```bash
pfoundry admin user delete USER_ID [--confirm]

# Example
pfoundry admin user delete john.doe@company.com --confirm
```

### Batch Get Users

```bash
pfoundry admin user batch-get USER_IDS...

# Max 500 user IDs

# Example
pfoundry admin user batch-get user1@company.com user2@company.com user3@company.com
```

## Group Commands

### List Groups

```bash
pfoundry admin group list [--format FORMAT]

# Example
pfoundry admin group list
```

### Get Group Info

```bash
pfoundry admin group get GROUP_ID [--format FORMAT]

# Example
pfoundry admin group get engineering-team
```

### Search Groups

```bash
pfoundry admin group search QUERY [--format FORMAT]

# Example
pfoundry admin group search "engineering"
```

### Create Group

```bash
pfoundry admin group create NAME [--description TEXT] [--org-rid TEXT]

# Example
pfoundry admin group create "Data Science Team" --description "Team for ML and analytics"
```

### Delete Group

```bash
pfoundry admin group delete GROUP_ID [--confirm]

# Example
pfoundry admin group delete old-team --confirm
```

### Batch Get Groups

```bash
pfoundry admin group batch-get GROUP_IDS...

# Max 500 group IDs

# Example
pfoundry admin group batch-get engineering-team data-team security-team
```

## Role Commands

### Get Role Info

```bash
pfoundry admin role get ROLE_ID [--format FORMAT]

# Example
pfoundry admin role get admin-role
```

### Batch Get Roles

```bash
pfoundry admin role batch-get ROLE_IDS...

# Max 500 role IDs

# Example
pfoundry admin role batch-get admin-role editor-role viewer-role
```

## Organization Commands

### Get Organization Info

```bash
pfoundry admin org get ORGANIZATION_ID [--format FORMAT]

# Example
pfoundry admin org get my-organization
```

### Create Organization

```bash
pfoundry admin org create NAME --enrollment-rid ENROLLMENT_RID [OPTIONS]

# Options:
#   --admin-id TEXT    Admin user IDs (can specify multiple)

# Example
pfoundry admin org create "New Organization" --enrollment-rid ri.enrollment.main.123 \
  --admin-id admin1@company.com --admin-id admin2@company.com
```

### Replace Organization

```bash
pfoundry admin org replace ORGANIZATION_RID NAME [OPTIONS]

# Options:
#   --description TEXT    New organization description
#   --confirm             Skip confirmation prompt

# Example
pfoundry admin org replace ri.compass.main.org.123 "Updated Org Name" \
  --description "Updated description" --confirm
```

### List Available Roles for Organization

```bash
pfoundry admin org available-roles ORGANIZATION_RID [--page-size N] [--page-token TEXT]

# Example
pfoundry admin org available-roles ri.compass.main.org.123 --page-size 50
```

## Marking Commands

### List Markings

```bash
pfoundry admin marking list [--page-size N] [--page-token TEXT] [--format FORMAT]

# Example
pfoundry admin marking list --format json --output markings.json
```

### Get Marking Info

```bash
pfoundry admin marking get MARKING_ID [--format FORMAT]

# Example
pfoundry admin marking get marking-confidential
```

### Create Marking

```bash
pfoundry admin marking create NAME [OPTIONS]

# Options:
#   --description TEXT    Marking description
#   --category-id TEXT    Category ID for the marking

# Example
pfoundry admin marking create "Confidential" --description "Confidential data marking"
```

### Replace Marking

```bash
pfoundry admin marking replace MARKING_ID NAME [OPTIONS]

# Options:
#   --description TEXT    New marking description
#   --confirm             Skip confirmation prompt

# Example
pfoundry admin marking replace marking-123 "Updated Name" --description "New description" --confirm
```

### Batch Get Markings

```bash
pfoundry admin marking batch-get MARKING_IDS...

# Max 500 marking IDs

# Example
pfoundry admin marking batch-get marking-1 marking-2 marking-3
```

## Audit Log Commands

Organization audit log files, read-only.

```bash
# List audit log files for an organization within a date range
pfoundry audit list ORGANIZATION_RID START_DATE [--end-date DATE] [--page-size N] [--format FORMAT]

# Download the content of one audit log file
pfoundry audit get ORGANIZATION_RID LOG_FILE_ID [--output FILE]

# Examples
pfoundry audit list ri.foundry.main.organization.abc123 2026-07-01 --end-date 2026-07-24
pfoundry audit get ri.foundry.main.organization.abc123 log-file-id-456 --output audit.json
```

## Common Patterns

### Audit users
```bash
# Export all users
pfoundry admin user list --format csv --output all_users.csv

# Search for admin users
pfoundry admin user search "admin" --format csv --output admins.csv
```

### User management workflow
```bash
# Get current user info
pfoundry admin user current

# Check user permissions
pfoundry admin user markings john.doe@company.com

# Search for specific users
pfoundry admin user search "data scientist"
```

### Group management
```bash
# List all groups
pfoundry admin group list --format json --output groups.json

# Create new team group
pfoundry admin group create "Analytics Team" --description "Business analytics team"

# Get group details
pfoundry admin group get analytics-team
```

### Security audit script
```bash
#!/bin/bash
# Export users and groups for audit
DATE=$(date +%Y%m%d)

pfoundry admin user list --format json --output "audit_users_${DATE}.json"
pfoundry admin group list --format json --output "audit_groups_${DATE}.json"
pfoundry admin user search "admin" --format csv --output "potential_admins_${DATE}.csv"

echo "Audit files generated for $DATE"
```
