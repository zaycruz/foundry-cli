"""
Global Branch commands (read-only).
"""

import typer
from typing import Optional
from rich.console import Console

from ..services.global_branching import (
    GlobalBranchNotFoundError,
    GlobalBranchService,
    GlobalBranchShapeError,
)
from ..utils.agent_output import agent_mode_enabled, buffer_agent_payload
from ..utils.completion import (
    complete_rid,
    complete_profile,
    complete_output_format,
    cache_rid,
)
from ..utils.formatting import OutputFormatter
from ..utils.progress import SpinnerProgressTracker
from ..auth.base import ProfileNotFoundError, MissingCredentialsError

app = typer.Typer(help="Inspect Ontology Global Branches")
console = Console()
formatter = OutputFormatter(console)


@app.command("get")
def get_branch(
    branch_rid: str = typer.Argument(
        ..., help="Global Branch Resource Identifier", autocompletion=complete_rid
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name", autocompletion=complete_profile
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json, csv, agent)",
        autocompletion=complete_output_format,
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Load one Global Branch by RID (read-only).

    Reads the internal branch-service API (PUT /branch/load/{branchRid}, an
    empty-body load). There is no list endpoint; load-by-RID only. The
    success response shape is UNVERIFIED on a live Foundry deployment and is passed
    through raw.
    """
    try:
        cache_rid(branch_rid)

        with SpinnerProgressTracker().track_spinner(
            f"Loading global branch {branch_rid}..."
        ):
            service = GlobalBranchService(profile=profile)
            branch = service.get_branch(branch_rid)

        if agent_mode_enabled() or format == "agent":
            buffer_agent_payload(
                branch,
                meta={
                    "operation": "view_global_branch",
                    "branch_rid": branch_rid,
                    "shape_verified": False,
                },
            )
        else:
            formatter.format_output([branch], format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except (GlobalBranchNotFoundError, GlobalBranchShapeError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error loading global branch: {e}[/red]")
        raise typer.Exit(1)
