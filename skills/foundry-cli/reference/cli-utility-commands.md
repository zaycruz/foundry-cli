# CLI Utility Commands

Agent-facing introspection of the CLI itself, plus shell alias management.
(For profiles, shell completion, the interactive shell, and `foundry hello`,
see `quick-start.md`.)

## Agent Introspection

```bash
# Emit every registered command as deterministic JSON (path, args, flags).
# This is the authoritative command surface; the reference docs are not.
foundry agent-manifest

# Score the command surface against Palantir's MCP tool catalog
foundry capabilities [--format FORMAT]

# Examples
foundry agent-manifest | jq '.commands | length'
foundry capabilities --format json
```

## Alias Commands

Aliases map short names to full CLI command lines.

```bash
# List all aliases
foundry alias list

# Create / overwrite an alias
foundry alias add NAME COMMAND [--force]

# Edit an existing alias
foundry alias edit NAME COMMAND

# Show one alias / resolve an alias to the real command
foundry alias show NAME
foundry alias resolve COMMAND

# Remove one alias / clear all aliases
foundry alias remove NAME [--confirm]
foundry alias clear [--confirm]

# Export to JSON / import from a JSON file
foundry alias export [--output FILE]
foundry alias import INPUT_FILE [--merge]

# Examples
foundry alias add ds "dataset get"
foundry alias resolve ds
foundry alias export --output aliases.json
foundry alias import aliases.json --merge
```
