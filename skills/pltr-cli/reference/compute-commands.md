# Compute Module Commands

Foundry Compute Module operations, backed by the internal gateways the
Palantir MCP compute-module tools use (client contract 2026-07-25 on a live Foundry deployment,
`the captured contract`). The MCP does NOT call the
module-group service at its own mount (`/module-group/api/...` is
`Route:RouteNotMounted` on every stack verified); these commands
deliberately never call it either. Instead:

- info, dev-mode, execute → `contour-backend-multiplexer/api/...`
- start, stop → `build2/api/...`
- logs → `foundry-telemetry-service/api/...`

Route mounts are contract-verified via their error contracts (403
`Contour:InsufficientPermission` / 400 `Build2:...`, never
`Route:RouteNotMounted`). The verification token lacks `deployed-apps:view/edit/submit`,
so no success payload has been observed for the contour/build2 endpoints:
success shapes are UNVERIFIED and passed through raw, with
`shape_verified: false` in the agent envelope. The `logs/read/v3` shape is
bundle-derived (only step 1 of the logs flow returned a live 200).

Write commands are plan-first: they print a dry-run plan by default and issue
no network request. A real mutation requires `--apply`; `stop` additionally
requires `--yes`.

## Get Compute Module Info (read-only)

```bash
pltr compute info DEPLOYED_APP_RID [--branch BRANCH] [--include status|config] [--format FORMAT]

# One internal GET per include entry against contour-backend-multiplexer:
#   status -> /deployed-apps/{rid}/{branch}/status
#   config -> /deployed-apps/{rid}/v2
# Default loads both.

# Example
pltr compute info ri.foundry.main.deployed-app.abc123 --include status
```

## Read Compute Module Logs (read-only)

```bash
pltr compute logs BUILD_JOB_RID [--from-inclusive MICROS] [--to-exclusive MICROS] \
    [--page-size-limit N] [--reverse] [--format FORMAT]

# Two-step telemetry flow: resolve the container/session via
# foundry-telemetry-service sessions/by-run-rids/get-batch, then read
# logs/read/v3 with microsecond-since-epoch timestamps. Defaults to the last
# 24 hours, chronological, 100 entries (max 1000). Step 2's shape is
# bundle-derived and NOT contract-verified; the response is passed through raw.

# Example
pltr compute logs ri.foundry.main.job.abc123 --page-size-limit 500
```

## Manage Compute Modules (plan-first)

```bash
pltr compute manage --action start --deployed-app-rid RID [--branch BRANCH] [--apply]
pltr compute manage --action stop --build-rid BUILD_RID [--apply] [--yes]
pltr compute manage --action dev-mode --deployed-app-rid RID [--branch BRANCH] \
    [--dev-mode-until ISO8601] [--apply]

# start: build2 POST /manager/submitBuild with the deployed-app RID passed as
#   a datasets jobSpecSelection (isRequired: true) — exactly as captured.
# stop: build2 DELETE /manager/builds/{buildRid} (no body).
# dev-mode: contour-backend-multiplexer PUT /deployed-apps/{rid}/{branch}/
#   dev-mode with {automaticUpgradesUntil: ISO-8601, max +5h}; omit
#   --dev-mode-until to send an empty body and DISABLE dev mode.
# Without --apply each action prints the dry-run plan and issues no request.

# Examples
pltr compute manage --action start --deployed-app-rid ri.foundry.main.deployed-app.abc123
pltr compute manage --action stop --build-rid ri.foundry.main.build.abc123 --apply --yes
pltr compute manage --action dev-mode --deployed-app-rid ri.foundry.main.deployed-app.abc123 \
    --dev-mode-until 2026-07-25T20:00:00Z --apply
```

## Execute a Compute Module Function (plan-first)

```bash
pltr compute execute DEPLOYED_APP_RID --query-type TYPE [--query JSON] \
    [--branch BRANCH] [--apply] [--format FORMAT]

# contour-backend-multiplexer POST /module-group-multiplexer/compute-modules/
# jobs/execute. Only works for FUNCTION-mode modules that are running. The
# response is a raw octet-stream (the function's return value, expected
# JSON); its shape is UNVERIFIED and passed through raw. Without --apply the
# command prints the dry-run plan and issues no network request.

# Example
pltr compute execute ri.foundry.main.deployed-app.abc123 \
    --query-type my-function --query '{"input": 1}' --apply
```
