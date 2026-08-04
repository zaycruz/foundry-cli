"""
Interactive shell (REPL) command for the foundry CLI.
Provides an interactive mode with tab completion and command history.
"""

import os
from pathlib import Path
from typing import Optional

import typer
from click_repl import repl  # type: ignore
from prompt_toolkit.history import FileHistory
from rich.console import Console

from ..config.profiles import ProfileManager

shell_app = typer.Typer(
    name="shell",
    help="Start an interactive shell session with tab completion and history",
)


def get_history_file() -> Path:
    """Get the path to the history file for the REPL."""
    config_dir = Path.home() / ".config" / "foundry"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "repl_history"


def get_prompt() -> str:
    """Get the prompt string for the REPL."""
    try:
        profile_manager = ProfileManager()
        current_profile = profile_manager.get_active_profile()
        if current_profile:
            return f"foundry ({current_profile})> "
        else:
            return "foundry> "
    except Exception:
        return "foundry> "


@shell_app.command()
def start(
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Auth profile to use for the session"
    ),
) -> None:
    """
    Start an interactive shell session for foundry CLI.

    Features:
    - Tab completion for all commands
    - Command history (persistent across sessions)
    - Current profile displayed in prompt
    - All foundry commands available without the 'foundry' prefix

    Examples:
        # Start interactive shell
        $ foundry shell

        # In the shell, run commands without 'foundry' prefix:
        foundry> dataset get ri.foundry.main.dataset.123
        foundry> ontology list
        foundry> sql execute "SELECT * FROM dataset LIMIT 10"

        # Exit the shell:
        foundry> exit
    """
    console = Console()

    # Set profile if specified
    if profile:
        os.environ["FOUNDRY_PROFILE"] = profile
        console.print(f"[green]Using profile: {profile}[/green]")

    # Welcome message
    console.print("\n[bold cyan]Welcome to foundry interactive shell![/bold cyan]")
    console.print("Type 'help' for available commands, 'exit' to quit.\n")

    # Import here to avoid circular dependency
    from ..cli import app as main_app

    # Convert Typer app to Click object and create context
    # This is the correct way to integrate click-repl with Typer
    from typer.main import get_command

    click_app = get_command(main_app)
    ctx = click_app.make_context("foundry", [])

    # Start the REPL with the Click context
    repl(
        ctx,
        prompt_kwargs={
            "message": get_prompt,
            "history": FileHistory(str(get_history_file())),
            "complete_while_typing": True,
            "enable_history_search": True,
        },
    )

    console.print("\n[cyan]Goodbye![/cyan]")


# Make 'start' the default command when just running 'foundry shell'
@shell_app.callback(invoke_without_command=True)
def shell_callback(
    ctx: typer.Context,
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Auth profile to use for the session"
    ),
) -> None:
    """Interactive shell mode with tab completion and command history."""
    if ctx.invoked_subcommand is None:
        start(profile=profile)


# Alternative command name for convenience
@shell_app.command("interactive", hidden=True)
def interactive_alias(
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Auth profile to use for the session"
    ),
) -> None:
    """Alias for 'start' command."""
    start(profile=profile)
