# Admin Audit and Access Review Workflow

Use this workflow for identity lifecycle and access review: establishing the acting identity, inventorying users and groups, reviewing role grants on Compass resources, investigating organization audit logs, and applying identity or permission changes. Every mutation is presented plan-first and requires an explicit confirmation step.

## Contract

This workflow guarantees that the agent:

- establishes the acting identity and target organization before any admin operation;
- captures a read-only evidence baseline before proposing any change;
- resolves principal UUIDs and role IDs from observed data, never from memory;
- presents every mutation as a plan with the exact apply command, and requires the explicit confirmation flag;
- reruns the same read after a mutation and reports the diff against the baseline.

It does not infer permissions it has not observed, and it does not treat a missing read command as proof that access does not exist.

Known capability gaps (documented, not worked around):

- The CLI exposes no group membership read or mutation commands (`foundry admin group` offers only `list`, `get`, `search`, `create`, `delete`, `batch-get`). Membership inspection, add, and remove are performed in the Foundry platform UI; record them in the plan and verification as out-of-band steps.
- `foundry resource-role grant` has no `--confirm` flag and applies immediately. Treat the read phases below as its only review gate, and never run it before the plan is accepted.
- `foundry audit` returns raw log files for an organization; it does not filter by user, action, or resource. Filtering is a local post-processing step.

## Phase 1: Establish identity and scope

Admin commands require admin permissions. Confirm the acting identity and the target organization first:

```bash
foundry admin user current --profile "$PROFILE" --format json
foundry admin org get "$ORGANIZATION_ID" --profile "$PROFILE" --format json
```

Record the acting user's ID and the organization RID from the output. Use the organization RID returned by the platform (for example `ri.foundry.main.organization.abc123`) for all subsequent audit and role commands. If `admin user current` lacks admin permissions, stop and report; do not probe further.

## Phase 2: Inventory users and groups (read-only)

Capture the baseline before any proposed change. Save artifacts for diffing:

```bash
# Full user inventory
foundry admin user list --profile "$PROFILE" --page-size 50 \
  --format json --output ./audit_users.json

# Targeted lookup
foundry admin user search "$QUERY" --profile "$PROFILE" --page-size 20 --format json
foundry admin user get "$USER_ID" --profile "$PROFILE" --format json
foundry admin user markings "$USER_ID" --profile "$PROFILE" --format json

# Batch resolution (max 500 IDs)
foundry admin user batch-get "$USER_ID_1" "$USER_ID_2" --profile "$PROFILE"

# Group inventory
foundry admin group list --profile "$PROFILE" --format json --output ./audit_groups.json
foundry admin group search "$QUERY" --profile "$PROFILE" --format json
foundry admin group get "$GROUP_ID" --profile "$PROFILE" --format json
```

Extract and record the principal UUID for each user or group that a later mutation will target. `foundry resource-role grant` and `revoke` require the principal UUID; an email address or display name is not accepted.

Group membership cannot be enumerated or changed through the CLI. If the review depends on membership, mark it as an out-of-band verification item for the Foundry platform UI.

## Phase 3: Review role grants on Compass resources (read-only)

List current grants on each in-scope resource, then resolve role IDs:

```bash
RESOURCE="ri.foundry.main.dataset.abc123"

foundry resource-role list "$RESOURCE" --profile "$PROFILE" \
  --format json --output ./audit_resource_roles.json

# Narrow by principal type when the grant list is large
foundry resource-role list "$RESOURCE" --principal-type User --profile "$PROFILE"
foundry resource-role list "$RESOURCE" --principal-type Group --profile "$PROFILE"

# Resolve role IDs discovered in the grant list (max 500 per call)
foundry admin role get "$ROLE_ID" --profile "$PROFILE" --format json
foundry admin role batch-get "$ROLE_ID_1" "$ROLE_ID_2" --profile "$PROFILE"

# Enumerate roles grantable in the organization
foundry admin org available-roles "$ORGANIZATION_RID" --profile "$PROFILE" \
  --page-size 50 --format json

# Review markings and access requirements gating the resource
foundry resource list-markings "$RESOURCE" --profile "$PROFILE" --format json
foundry resource access-requirements "$RESOURCE" --profile "$PROFILE" --format json
```

A role grant is only half of effective access. Markings and organization requirements from `access-requirements` gate the resource independently; report both.

## Phase 4: Investigate with organization audit logs (read-only)

Audit logs are organization-scoped raw log files. List files for a date range, then download the specific files to inspect:

```bash
# 1. List available audit log files for the window
foundry audit list "$ORGANIZATION_RID" 2026-07-01 \
  --end-date 2026-07-24 \
  --profile "$PROFILE" --format json --output ./audit_log_files.json

# 2. Download the content of one log file
foundry audit get "$ORGANIZATION_RID" "$LOG_FILE_ID" \
  --profile "$PROFILE" --output ./audit_log_2026-07-01.json
```

Take `$LOG_FILE_ID` from the `audit list` output; never construct it by hand. Filter the downloaded files locally (for example with `jq`) for the user, action, or resource under investigation. Keep date windows narrow: a wide `--end-date` range produces many files that must each be downloaded and searched.

## Phase 5: Apply mutations plan-first

Before any mutation, run `workflows/change-impact-assessment.md` when the change touches a Foundry resource (a `resource-role` grant or revoke on a Compass resource counts). For pure identity changes (user delete, token revocation), the Phase 2 baseline is the impact record.

Present the plan to the operator with: the principal UUID, the role ID, the resource RID, the baseline evidence path, and the exact apply command. Execute only after explicit acceptance.

Commands without a confirmation flag (`admin group create`, `resource-role grant`) apply immediately; commands with `--confirm` prompt by default and the flag skips the prompt. Omit `--confirm` only when an interactive operator will answer the prompt.

```bash
# Revoke all tokens for a user (prompts without --confirm)
foundry admin user revoke-tokens "$USER_ID" --profile "$PROFILE" --confirm

# Delete a user (prompts without --confirm)
foundry admin user delete "$USER_ID" --profile "$PROFILE" --confirm

# Create a group (applies immediately, no confirmation flag)
foundry admin group create "$GROUP_NAME" \
  --description "$DESCRIPTION" --org-rid "$ORGANIZATION_RID" --profile "$PROFILE"

# Delete a group (prompts without --confirm)
foundry admin group delete "$GROUP_ID" --profile "$PROFILE" --confirm

# Grant a role on a resource (applies immediately, no confirmation flag;
# principal-id must be a UUID)
foundry resource-role grant "$RESOURCE" \
  --principal-id "$PRINCIPAL_UUID" --principal-type Group --role "$ROLE_ID" \
  --profile "$PROFILE"

# Revoke a role on a resource (prompts without --confirm)
foundry resource-role revoke "$RESOURCE" \
  --principal-id "$PRINCIPAL_UUID" --principal-type Group --role "$ROLE_ID" \
  --profile "$PROFILE" --confirm
```

Group membership add/remove is not available in the CLI. When the plan includes membership changes, execute them in the Foundry platform UI between the CLI steps and record them in the report.

## Phase 6: Re-verify against the baseline

Rerun the same read commands from Phases 2 and 3 after the mutation and diff against the saved artifacts:

```bash
foundry admin user get "$USER_ID" --profile "$PROFILE" --format json
foundry resource-role list "$RESOURCE" --profile "$PROFILE" --format json \
  --output ./audit_resource_roles_after.json

diff ./audit_resource_roles.json ./audit_resource_roles_after.json
```

For user deletion, expect `admin user get` to fail; record the failure as the verification evidence. For token revocation, no CLI read confirms token state; report the revocation as applied-but-unverifiable and, when relevant, corroborate with a Phase 4 audit-log pull for the following day.

## Output Format

Report:

1. acting identity, profile, and organization RID;
2. user and group inventory summary, with artifact paths;
3. role grants per resource, with resolved role names and the access requirements gating each resource;
4. audit-log findings, with log file IDs and local file paths;
5. the mutation plan: exact commands, principals, roles, resources, and which steps are out-of-band (group membership);
6. applied mutations with their confirmation flags;
7. post-change diff against the baseline and any verification gaps.

## Anti-Patterns

- Running an identity or permission mutation before capturing the Phase 2/3 baseline
- Passing an email or display name to `resource-role grant`/`revoke` instead of a resolved principal UUID
- Assuming `resource-role grant` prompts for confirmation; it applies immediately
- Inventing group membership add/remove commands; the CLI has none
- Treating a resource-role grant as sufficient access without checking `access-requirements` and markings
- Constructing audit log file IDs instead of taking them from `audit list` output
- Pulling a wide audit date range when a narrow window answers the question
- Reporting a deleted user's access as verified without a post-change diff or audit-log corroboration
- Skipping `workflows/change-impact-assessment.md` before a permission change on a Compass resource
