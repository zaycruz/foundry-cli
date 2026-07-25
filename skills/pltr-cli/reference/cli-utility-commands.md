# CLI Utility Commands

Agent-facing introspection of the CLI itself, plus shell alias management.
(For profiles, shell completion, the interactive shell, and `pltr hello`,
see `quick-start.md`.)

## Agent Introspection

```bash
# Emit every registered command as deterministic JSON (path, args, flags).
# This is the authoritative command surface; the reference docs are not.
pltr agent-manifest

# Score the command surface against Palantir's MCP tool catalog
pltr capabilities [--format FORMAT]

# Examples
pltr agent-manifest | jq '.commands | length'
pltr capabilities --format json
```

## Alias Commands

Aliases map short names to full CLI command lines.

```bash
# List all aliases
pltr alias list

# Create / overwrite an alias
pltr alias add NAME COMMAND [--force]

# Edit an existing alias
pltr alias edit NAME COMMAND

# Show one alias / resolve an alias to the real command
pltr alias show NAME
pltr alias resolve COMMAND

# Remove one alias / clear all aliases
pltr alias remove NAME [--confirm]
pltr alias clear [--confirm]

# Export to JSON / import from a JSON file
pltr alias export [--output FILE]
pltr alias import INPUT_FILE [--merge]

# Examples
pltr alias add ds "dataset get"
pltr alias resolve ds
pltr alias export --output aliases.json
pltr alias import aliases.json --merge
```
