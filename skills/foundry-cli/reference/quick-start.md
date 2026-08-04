# Quick Start & Authentication

## Installation

```bash
# Install from git (not published to PyPI)
uv pip install "git+https://github.com/zaycruz/foundry-cli"

# Or with pipx (isolated)
pipx install "git+https://github.com/zaycruz/foundry-cli"

# Verify installation
foundry --version
```

## Authentication Setup

### Token Authentication (Recommended)

1. Get your API token from Foundry web UI (Settings > API Tokens)
2. Configure foundry-cli:

```bash
foundry configure configure
```

Enter:
- Foundry hostname (e.g., `foundry.company.com`)
- Authentication type: `token`
- API token
- Profile name (e.g., `production`)

### Environment Variables (CI/CD)

```bash
export FOUNDRY_TOKEN="your-token"
export FOUNDRY_HOST="foundry.company.com"
```

### OAuth2 Authentication

```bash
foundry configure configure --profile oauth-prod --auth-type oauth \
  --host foundry.company.com \
  --client-id "your-client-id" \
  --client-secret "your-client-secret"
```

## Verify Connection

```bash
foundry verify
# Expected: "Authentication successful!"
```

## Multiple Profiles

```bash
# Configure multiple profiles
foundry configure configure --profile production
foundry configure configure --profile development

# List profiles
foundry configure list

# Set default profile
foundry configure use production

# Mark a profile as the default without switching sessions
foundry configure set-default production

# Use specific profile
foundry verify --profile development
```

## Profile Management

```bash
# List all profiles
foundry configure list

# Delete profile
foundry configure delete old-profile --force
```

## Output Formats

```bash
foundry <command> --format table    # Rich table (default)
foundry <command> --format json     # JSON
foundry <command> --format csv      # CSV
foundry <command> --output file.csv # Save to file
```

## Interactive Shell

```bash
foundry shell --profile production

# Explicit equivalent:
foundry shell start --profile production

# In shell mode:
foundry (production)> admin user current
foundry (production)> sql execute "SELECT 1"
foundry (production)> exit
```

## Shell Completion

```bash
foundry completion install           # Auto-detect shell
foundry completion install --shell zsh
foundry completion install --shell bash

# Print the completion script without installing it (manual setup, debugging)
foundry completion show --shell zsh

# Remove installed completions
foundry completion uninstall
```

## First Commands to Try

```bash
# Sanity-check the CLI itself (no network call)
foundry hello

# Check current user
foundry admin user current

# List ontologies
foundry ontology list

# Simple SQL query
foundry sql execute "SELECT 1 as test"

# Search builds
foundry orchestration builds search
```

## Troubleshooting

### Authentication Failed
- Token expired: Regenerate in Foundry web UI
- Wrong hostname: Don't include `https://`
- Network issues: Check VPN connection

### Command Not Found
- Ensure Python scripts directory is in PATH
- Check virtual environment is activated
