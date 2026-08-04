# Docs Commands

Read the real Foundry documentation corpus from the terminal. All commands
are read-only; search is bounded and honestly partial.

## Search and Summaries

```bash
# Search the real documentation corpus (bounded, honestly partial)
foundry docs search QUERY [--limit N] [--fetch-pages] [--format FORMAT]

# Summarize the corpus by section from the real sitemap
foundry docs summaries [--section NAME] [--with-overviews] [--section-limit N] [--format FORMAT]

# Load one documentation page as verbatim markdown
foundry docs page PAGE [--format FORMAT]

# Examples
foundry docs search "python transforms incremental" --limit 10
foundry docs summaries --section transforms --with-overviews
foundry docs page /docs/foundry/data-integration/python-transforms
```

## Topic Pages

Each of these prints a curated documentation page:

```bash
foundry docs compute                  # Compute modules
foundry docs custom-widgets           # Custom widgets
foundry docs ml                       # Machine learning (model integration)
foundry docs osdk-react-components    # OSDK React applications
foundry docs python-transforms        # Python transforms
foundry docs spark-profile            # Spark profiles
foundry docs typescript-v1-functions  # TypeScript v1 functions
foundry docs typescript-v2-functions  # TypeScript v2 functions

# Example
foundry docs python-transforms --format json
```
