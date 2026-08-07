# CLI Utility Commands

Agent-facing introspection of the CLI itself, plus shell alias management.
(For profiles, shell completion, the interactive shell, and `pfoundry hello`,
see `quick-start.md`.)

## Agent Introspection

```bash
# Emit every registered command as deterministic JSON (path, args, flags).
# This is the authoritative command surface; the reference docs are not.
pfoundry agent-manifest

# Score the command surface against Palantir's MCP tool catalog
pfoundry capabilities [--format FORMAT]

# Examples
pfoundry agent-manifest | jq '.commands | length'
pfoundry capabilities --format json
```

## Alias Commands

Aliases map short names to full CLI command lines.

```bash
# List all aliases
pfoundry alias list

# Create / overwrite an alias
pfoundry alias add NAME COMMAND [--force]

# Edit an existing alias
pfoundry alias edit NAME COMMAND

# Show one alias / resolve an alias to the real command
pfoundry alias show NAME
pfoundry alias resolve COMMAND

# Remove one alias / clear all aliases
pfoundry alias remove NAME [--confirm]
pfoundry alias clear [--confirm]

# Export to JSON / import from a JSON file
pfoundry alias export [--output FILE]
pfoundry alias import INPUT_FILE [--merge]

# Examples
pfoundry alias add ds "dataset get"
pfoundry alias resolve ds
pfoundry alias export --output aliases.json
pfoundry alias import aliases.json --merge
```
