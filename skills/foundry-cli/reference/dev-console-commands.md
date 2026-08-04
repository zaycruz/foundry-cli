# Dev Console, OSDK, and Platform SDK Commands

Headless equivalents of the Foundry developer-console surface: third-party
application inspection, OSDK definition reads, SDK install, and local code
generation. Mutation posture is deliberate and documented per command —
several vendor MCP actions have no verified headless write contract, and
this CLI refuses to guess request bodies.

## Third-Party Application Commands

### Get Application

```bash
foundry third-party-apps get APPLICATION_RID [--format FORMAT]

# Example
foundry third-party-apps get ri.foundry.third-party-application.main.application.abc123
```

## Dev Console Commands

### Connect (read-only divergence)

```bash
foundry dev-console connect APPLICATION_RID [--format FORMAT]

# Documented divergence from the vendor MCP: connect_to_dev_console_app is
# an interactive IDE/workspace action with no headless equivalent, so this
# command is its honest READ-ONLY form. It reads the application via the
# VERIFIED TPAS getApplication endpoint and reports the connection context
# (client/credentials type, OAuth grants, redirect URLs, data scope). No
# session is established and nothing is mutated.

# Example
foundry dev-console connect ri.foundry.third-party-application.main.application.abc123
```

### OSDK Definition (read-only)

```bash
foundry dev-console osdk definition APPLICATION_RID [--version VERSION] [--format FORMAT]

# Reads the application's generated OSDK definition.

# Example
foundry dev-console osdk definition ri.foundry.third-party-application.main.application.abc123
```

### SDK Generate (dry-run by default; --apply mutates)

```bash
foundry dev-console sdk generate APPLICATION_RID [--apply] [--no-wait] [--timeout SECONDS] [--format FORMAT]

# Mints a new OSDK version from the app's current applicationVersion, backed
# by the contract-derived, contract-verified createSdkV2 contract
# (the captured contract,  against a live deployment):
#   1. GET  /third-party-application-service/api/applications/{applicationRid}
#      -> read metadata.applicationVersion
#   2. POST /third-party-application-service/api/application-sdks/v2/{applicationRid}
#      body {"applicationVersion": N, "npm": {}} (exactly these two keys;
#      unknown top-level keys are rejected with 422)
#   3. Poll GET /third-party-application-service/api/application-sdks/{rid}
#      (listSdks) until the minted record's npm.status.type turns terminal
#      (requested -> inProgress -> success; ~24s observed). The MCP's
#      /latest?sdkType=NPM&sdkStatus=REQUESTED confirmation read is NOT
#      usable as the completion poll: it returns 204 No Content as soon as
#      the record leaves "requested" (contract-verified).
#
# Without --apply the command prints the dry-run plan (resolved version and
# exact request body) and sends nothing mutating. --apply issues the POST and
# polls to a terminal status unless --no-wait is given. Exit codes: 0 plan /
# requested / success, 1 generation failed, 2 polling timeout (the version
# was still minted server-side). The MCP's scope-patch PUT is NOT needed for
# a pure regenerate from the current app version.

# Examples
foundry dev-console sdk generate ri.foundry.third-party-application.main.application.abc123
foundry dev-console sdk generate ri.foundry.third-party-application.main.application.abc123 --apply
```

### SDK Install (dry-run by default)

```bash
foundry dev-console sdk install APPLICATION_RID [--version VERSION] [--yes] [--target DIR] [--dry-run]

# Resolves the app's SDK repository via the verified getSdkRepositoryRid
# endpoint and installs from the stack's Artifacts npm/pypi registry.
# Non-destructive by default: without --yes or --target the command prints
# the resolved plan (dry-run) and changes nothing.

# Example
foundry dev-console sdk install ri.foundry.third-party-application.main.application.abc123 --yes
```

### Convert OSDK to React (local codegen)

```bash
foundry dev-console convert-osdk-react APPLICATION_RID [--output-dir DIR] [--force]

# Local codegen, never network-mutating: reads the app's data scope via the
# VERIFIED TPAS getApplication endpoint and the ontology's object types via
# the public v2 API, then writes one typed presentational <ApiName>Card.tsx
# per in-scope object type plus an index.ts barrel. Existing files are never
# overwritten without --force.

# Example
foundry dev-console convert-osdk-react ri.foundry.third-party-application.main.application.abc123 \
    --output-dir ./src/components
```

## OSDK Helper Commands

```bash
# Codegen context for the live ontology (object types, properties, links)
foundry osdk context [--ontology ONTOLOGY_RID] [--format FORMAT]

# Real OSDK usage examples bound to the live ontology
foundry osdk examples [--ontology ONTOLOGY_RID] [--language LANG] [--format FORMAT]

# Examples
foundry osdk context
foundry osdk examples --language typescript
```

## Platform SDK Introspection

Inspect the installed `foundry-platform-sdk` itself.

```bash
# Every namespace, resource, and method of the installed SDK
foundry platform-sdk api list [--format FORMAT]

# Verbatim docstring/signature for one SDK API (dotted path)
foundry platform-sdk api reference DOTTED_PATH [--format FORMAT]

# Examples
foundry platform-sdk api list
foundry platform-sdk api reference ontologies.Ontology.ObjectType.list
```
