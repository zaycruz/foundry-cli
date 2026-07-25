# Docs Commands

Read the real Foundry documentation corpus from the terminal. All commands
are read-only; search is bounded and honestly partial.

## Search and Summaries

```bash
# Search the real documentation corpus (bounded, honestly partial)
pltr docs search QUERY [--limit N] [--fetch-pages] [--format FORMAT]

# Summarize the corpus by section from the real sitemap
pltr docs summaries [--section NAME] [--with-overviews] [--section-limit N] [--format FORMAT]

# Load one documentation page as verbatim markdown
pltr docs page PAGE [--format FORMAT]

# Examples
pltr docs search "python transforms incremental" --limit 10
pltr docs summaries --section transforms --with-overviews
pltr docs page /docs/foundry/data-integration/python-transforms
```

## Topic Pages

Each of these prints a curated documentation page:

```bash
pltr docs compute                  # Compute modules
pltr docs custom-widgets           # Custom widgets
pltr docs ml                       # Machine learning (model integration)
pltr docs osdk-react-components    # OSDK React applications
pltr docs python-transforms        # Python transforms
pltr docs spark-profile            # Spark profiles
pltr docs typescript-v1-functions  # TypeScript v1 functions
pltr docs typescript-v2-functions  # TypeScript v2 functions

# Example
pltr docs python-transforms --format json
```
