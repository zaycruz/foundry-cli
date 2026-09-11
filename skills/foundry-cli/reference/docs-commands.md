# Docs Commands

Read the real Foundry documentation corpus from the terminal. All commands
are read-only; search is bounded and honestly partial.

## Search and Summaries

```bash
# Search the real documentation corpus (bounded, honestly partial)
pfoundry docs search QUERY [--limit N] [--fetch-pages] [--format FORMAT]

# Summarize the corpus by section from the real sitemap
pfoundry docs summaries [--section NAME] [--with-overviews] [--section-limit N] [--format FORMAT]

# Load one documentation page as verbatim markdown
pfoundry docs page PAGE [--format FORMAT]

# Examples
pfoundry docs search "python transforms incremental" --limit 10
pfoundry docs summaries --section transforms --with-overviews
pfoundry docs page /docs/foundry/data-integration/python-transforms
```

## Topic Pages

Each of these prints a curated documentation page:

```bash
pfoundry docs compute                  # Compute modules
pfoundry docs custom-widgets           # Custom widgets
pfoundry docs ml                       # Machine learning (model integration)
pfoundry docs osdk-react-components    # OSDK React applications
pfoundry docs python-transforms        # Python transforms
pfoundry docs spark-profile            # Spark profiles
pfoundry docs typescript-v1-functions  # TypeScript v1 functions
pfoundry docs typescript-v2-functions  # TypeScript v2 functions

# Example
pfoundry docs python-transforms --format json
```
