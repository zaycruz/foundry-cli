"""Main entry point for foundry CLI."""

import os
import sys

# Handle shell completion before importing the main app
if "_PFOUNDRY_COMPLETE" in os.environ:
    # Import Click's completion handling
    from click.shell_completion import shell_complete
    import typer
    from foundry_cli.cli import app

    # Convert Typer app to Click command
    click_app = typer.main.get_command(app)

    # Get the completion instruction from environment
    complete_var = "_PFOUNDRY_COMPLETE"
    instruction = os.environ.get(complete_var, "")

    # Run Click's completion
    exit_code = shell_complete(click_app, {}, "pfoundry", complete_var, instruction)
    sys.exit(exit_code)

# Normal CLI execution
from foundry_cli.cli import main_entrypoint
from foundry_cli.utils.alias_resolver import inject_alias_resolution

if __name__ == "__main__":
    # Resolve aliases before running the app
    inject_alias_resolution()
    main_entrypoint()
