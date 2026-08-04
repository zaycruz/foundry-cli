# Widgets Commands

Inspect custom widget sets and their releases, and manage widget dev mode.

## Widget Set Commands

```bash
# Details of a widget set
foundry widgets get WIDGET_SET_RID [--format FORMAT]

# Details of the widget repository backing a code repository
foundry widgets repository get REPOSITORY_RID [--format FORMAT]

# Examples
foundry widgets get ri.widgets.main.widget-set.abc123
foundry widgets repository get ri.stemma.main.repository.abc123
```

## Release Commands

```bash
# List releases for a widget set
foundry widgets release list WIDGET_SET_RID [--page-size N] [--format FORMAT]

# Get one release
foundry widgets release get WIDGET_SET_RID RELEASE_VERSION [--format FORMAT]

# Delete a release
foundry widgets release delete WIDGET_SET_RID RELEASE_VERSION [--yes]

# Examples
foundry widgets release list ri.widgets.main.widget-set.abc123
foundry widgets release get ri.widgets.main.widget-set.abc123 1.0.0
foundry widgets release delete ri.widgets.main.widget-set.abc123 1.0.0 --yes
```

## Dev Mode

```bash
# Enable widget dev mode for the current user
foundry widgets dev-mode enable [--format FORMAT]
```
