# Admin Commands

User, group, role, and organization management. **Requires admin permissions**.

## User Commands

### List Users

```bash
foundry admin user list [--page-size N] [--page-token TEXT] [--format FORMAT]

# Example
foundry admin user list --page-size 50 --format csv --output users.csv
```

### Get User Info

```bash
foundry admin user get USER_ID [--format FORMAT]

# Example
foundry admin user get john.doe@company.com
```

### Current User

```bash
foundry admin user current [--format FORMAT]

# Example
foundry admin user current --format json
```

### Search Users

```bash
foundry admin user search QUERY [--page-size N] [--format FORMAT]

# Example
foundry admin user search "john" --page-size 20
```

### Get User Markings/Permissions

```bash
foundry admin user markings USER_ID [--format FORMAT]

# Example
foundry admin user markings john.doe@company.com
```

### Revoke User Tokens

```bash
foundry admin user revoke-tokens USER_ID [--confirm]

# Example
foundry admin user revoke-tokens john.doe@company.com --confirm
```

### Delete User

```bash
foundry admin user delete USER_ID [--confirm]

# Example
foundry admin user delete john.doe@company.com --confirm
```

### Batch Get Users

```bash
foundry admin user batch-get USER_IDS...

# Max 500 user IDs

# Example
foundry admin user batch-get user1@company.com user2@company.com user3@company.com
```

## Group Commands

### List Groups

```bash
foundry admin group list [--format FORMAT]

# Example
foundry admin group list
```

### Get Group Info

```bash
foundry admin group get GROUP_ID [--format FORMAT]

# Example
foundry admin group get engineering-team
```

### Search Groups

```bash
foundry admin group search QUERY [--format FORMAT]

# Example
foundry admin group search "engineering"
```

### Create Group

```bash
foundry admin group create NAME [--description TEXT] [--org-rid TEXT]

# Example
foundry admin group create "Data Science Team" --description "Team for ML and analytics"
```

### Delete Group

```bash
foundry admin group delete GROUP_ID [--confirm]

# Example
foundry admin group delete old-team --confirm
```

### Batch Get Groups

```bash
foundry admin group batch-get GROUP_IDS...

# Max 500 group IDs

# Example
foundry admin group batch-get engineering-team data-team security-team
```

## Role Commands

### Get Role Info

```bash
foundry admin role get ROLE_ID [--format FORMAT]

# Example
foundry admin role get admin-role
```

### Batch Get Roles

```bash
foundry admin role batch-get ROLE_IDS...

# Max 500 role IDs

# Example
foundry admin role batch-get admin-role editor-role viewer-role
```

## Organization Commands

### Get Organization Info

```bash
foundry admin org get ORGANIZATION_ID [--format FORMAT]

# Example
foundry admin org get my-organization
```

### Create Organization

```bash
foundry admin org create NAME --enrollment-rid ENROLLMENT_RID [OPTIONS]

# Options:
#   --admin-id TEXT    Admin user IDs (can specify multiple)

# Example
foundry admin org create "New Organization" --enrollment-rid ri.enrollment.main.123 \
  --admin-id admin1@company.com --admin-id admin2@company.com
```

### Replace Organization

```bash
foundry admin org replace ORGANIZATION_RID NAME [OPTIONS]

# Options:
#   --description TEXT    New organization description
#   --confirm             Skip confirmation prompt

# Example
foundry admin org replace ri.compass.main.org.123 "Updated Org Name" \
  --description "Updated description" --confirm
```

### List Available Roles for Organization

```bash
foundry admin org available-roles ORGANIZATION_RID [--page-size N] [--page-token TEXT]

# Example
foundry admin org available-roles ri.compass.main.org.123 --page-size 50
```

## Marking Commands

### List Markings

```bash
foundry admin marking list [--page-size N] [--page-token TEXT] [--format FORMAT]

# Example
foundry admin marking list --format json --output markings.json
```

### Get Marking Info

```bash
foundry admin marking get MARKING_ID [--format FORMAT]

# Example
foundry admin marking get marking-confidential
```

### Create Marking

```bash
foundry admin marking create NAME [OPTIONS]

# Options:
#   --description TEXT    Marking description
#   --category-id TEXT    Category ID for the marking

# Example
foundry admin marking create "Confidential" --description "Confidential data marking"
```

### Replace Marking

```bash
foundry admin marking replace MARKING_ID NAME [OPTIONS]

# Options:
#   --description TEXT    New marking description
#   --confirm             Skip confirmation prompt

# Example
foundry admin marking replace marking-123 "Updated Name" --description "New description" --confirm
```

### Batch Get Markings

```bash
foundry admin marking batch-get MARKING_IDS...

# Max 500 marking IDs

# Example
foundry admin marking batch-get marking-1 marking-2 marking-3
```

## Audit Log Commands

Organization audit log files, read-only.

```bash
# List audit log files for an organization within a date range
foundry audit list ORGANIZATION_RID START_DATE [--end-date DATE] [--page-size N] [--format FORMAT]

# Download the content of one audit log file
foundry audit get ORGANIZATION_RID LOG_FILE_ID [--output FILE]

# Examples
foundry audit list ri.foundry.main.organization.abc123 2026-07-01 --end-date 2026-07-24
foundry audit get ri.foundry.main.organization.abc123 log-file-id-456 --output audit.json
```

## Common Patterns

### Audit users
```bash
# Export all users
foundry admin user list --format csv --output all_users.csv

# Search for admin users
foundry admin user search "admin" --format csv --output admins.csv
```

### User management workflow
```bash
# Get current user info
foundry admin user current

# Check user permissions
foundry admin user markings john.doe@company.com

# Search for specific users
foundry admin user search "data scientist"
```

### Group management
```bash
# List all groups
foundry admin group list --format json --output groups.json

# Create new team group
foundry admin group create "Analytics Team" --description "Business analytics team"

# Get group details
foundry admin group get analytics-team
```

### Security audit script
```bash
#!/bin/bash
# Export users and groups for audit
DATE=$(date +%Y%m%d)

foundry admin user list --format json --output "audit_users_${DATE}.json"
foundry admin group list --format json --output "audit_groups_${DATE}.json"
foundry admin user search "admin" --format csv --output "potential_admins_${DATE}.csv"

echo "Audit files generated for $DATE"
```
