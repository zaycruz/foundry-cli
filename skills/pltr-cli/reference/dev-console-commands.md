# Dev Console, OSDK, and Platform SDK Commands

Headless equivalents of the Foundry developer-console surface: third-party
application inspection, OSDK definition reads, SDK install, and local code
generation. Mutation posture is deliberate and documented per command —
several vendor MCP actions have no verified headless write contract, and
this CLI refuses to guess request bodies.

## Third-Party Application Commands

### Get Application

```bash
pltr third-party-apps get APPLICATION_RID [--format FORMAT]

# Example
pltr third-party-apps get ri.foundry.third-party-application.main.application.abc123
```

## Dev Console Commands

### Connect (read-only divergence)

```bash
pltr dev-console connect APPLICATION_RID [--format FORMAT]

# Documented divergence from the vendor MCP: connect_to_dev_console_app is
# an interactive IDE/workspace action with no headless equivalent, so this
# command is its honest READ-ONLY form. It reads the application via the
# VERIFIED TPAS getApplication endpoint and reports the connection context
# (client/credentials type, OAuth grants, redirect URLs, data scope). No
# session is established and nothing is mutated.

# Example
pltr dev-console connect ri.foundry.third-party-application.main.application.abc123
```

### OSDK Definition (read-only)

```bash
pltr dev-console osdk definition APPLICATION_RID [--version VERSION] [--format FORMAT]

# Reads the application's generated OSDK definition.

# Example
pltr dev-console osdk definition ri.foundry.third-party-application.main.application.abc123
```

### SDK Generate (never mutates)

```bash
pltr dev-console sdk generate APPLICATION_RID [--format FORMAT]

# Deliberate no-mutation posture: the backing endpoint
# (POST /application-sdks/v2/{applicationRid}, createSdkV2) is catalog-only
# -- read-safe probes show strict deserialization but the required-field set
# is not disclosed, and a valid body would create a real SDK version. Per
# repo rules no mutation ships without a verified contract, so this command
# reads the current SDK records (VERIFIED listSdks) and exits 2 with the
# exact evidence instead of generating anything.

# Example
pltr dev-console sdk generate ri.foundry.third-party-application.main.application.abc123
```

### SDK Install (dry-run by default)

```bash
pltr dev-console sdk install APPLICATION_RID [--version VERSION] [--yes] [--target DIR] [--dry-run]

# Resolves the app's SDK repository via the verified getSdkRepositoryRid
# endpoint and installs from the stack's Artifacts npm/pypi registry.
# Non-destructive by default: without --yes or --target the command prints
# the resolved plan (dry-run) and changes nothing.

# Example
pltr dev-console sdk install ri.foundry.third-party-application.main.application.abc123 --yes
```

### Convert OSDK to React (local codegen)

```bash
pltr dev-console convert-osdk-react APPLICATION_RID [--output-dir DIR] [--force]

# Local codegen, never network-mutating: reads the app's data scope via the
# VERIFIED TPAS getApplication endpoint and the ontology's object types via
# the public v2 API, then writes one typed presentational <ApiName>Card.tsx
# per in-scope object type plus an index.ts barrel. Existing files are never
# overwritten without --force.

# Example
pltr dev-console convert-osdk-react ri.foundry.third-party-application.main.application.abc123 \
    --output-dir ./src/components
```

## OSDK Helper Commands

```bash
# Codegen context for the live ontology (object types, properties, links)
pltr osdk context [--ontology ONTOLOGY_RID] [--format FORMAT]

# Real OSDK usage examples bound to the live ontology
pltr osdk examples [--ontology ONTOLOGY_RID] [--language LANG] [--format FORMAT]

# Examples
pltr osdk context
pltr osdk examples --language typescript
```

## Platform SDK Introspection

Inspect the installed `foundry-platform-sdk` itself.

```bash
# Every namespace, resource, and method of the installed SDK
pltr platform-sdk api list [--format FORMAT]

# Verbatim docstring/signature for one SDK API (dotted path)
pltr platform-sdk api reference DOTTED_PATH [--format FORMAT]

# Examples
pltr platform-sdk api list
pltr platform-sdk api reference ontologies.Ontology.ObjectType.list
```
