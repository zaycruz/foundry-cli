# Quick Start & Authentication

## Installation

```bash
# Install from git (not published to PyPI)
uv pip install "git+https://github.com/zaycruz/foundry-cli"

# Or with pipx (isolated)
pipx install "git+https://github.com/zaycruz/foundry-cli"

# Verify installation
pfoundry --version
```

## Authentication Setup

### Token Authentication (Recommended)

1. Get your API token from Foundry web UI (Settings > API Tokens)
2. Configure foundry-cli:

```bash
pfoundry configure configure
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
pfoundry configure configure --profile oauth-prod --auth-type oauth \
  --host foundry.company.com \
  --client-id "your-client-id" \
  --client-secret "your-client-secret"
```

## Verify Connection

```bash
pfoundry verify
# Expected: "Authentication successful!"
```

## Multiple Profiles

```bash
# Configure multiple profiles
pfoundry configure configure --profile production
pfoundry configure configure --profile development

# List profiles
pfoundry configure list

# Set default profile
pfoundry configure use production

# Mark a profile as the default without switching sessions
pfoundry configure set-default production

# Use specific profile
pfoundry verify --profile development
```

## Profile Management

```bash
# List all profiles
pfoundry configure list

# Delete profile
pfoundry configure delete old-profile --force
```

## Output Formats

```bash
pfoundry <command> --format table    # Rich table (default)
pfoundry <command> --format json     # JSON
pfoundry <command> --format csv      # CSV
pfoundry <command> --output file.csv # Save to file
```

## Interactive Shell

```bash
pfoundry shell --profile production

# Explicit equivalent:
pfoundry shell start --profile production

# In shell mode:
pfoundry (production)> admin user current
pfoundry (production)> sql execute "SELECT 1"
pfoundry (production)> exit
```

## Shell Completion

```bash
pfoundry completion install           # Auto-detect shell
pfoundry completion install --shell zsh
pfoundry completion install --shell bash

# Print the completion script without installing it (manual setup, debugging)
pfoundry completion show --shell zsh

# Remove installed completions
pfoundry completion uninstall
```

## First Commands to Try

```bash
# Sanity-check the CLI itself (no network call)
pfoundry hello

# Check current user
pfoundry admin user current

# List ontologies
pfoundry ontology list

# Simple SQL query
pfoundry sql execute "SELECT 1 as test"

# Search builds
pfoundry orchestration builds search
```

## Troubleshooting

### Authentication Failed
- Token expired: Regenerate in Foundry web UI
- Wrong hostname: Don't include `https://`
- Network issues: Check VPN connection

### Command Not Found
- Ensure Python scripts directory is in PATH
- Check virtual environment is activated
