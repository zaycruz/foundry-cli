"""
Global Branch commands (read-only loads; plan-first writes).
"""

import typer
from typing import Optional
from rich.console import Console

from ..services.global_branching import (
    GlobalBranchNotFoundError,
    GlobalBranchService,
    GlobalBranchShapeError,
)
from ..utils.agent_output import (
    agent_mode_enabled,
    buffer_agent_payload,
    require_confirmation,
)
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


@app.command("create")
def create_branch(
    display_name: str = typer.Argument(..., help="Branch display name"),
    ontology_rid: str = typer.Option(
        ...,
        "--ontology-rid",
        help="Ontology RID the branch forks",
        autocompletion=complete_rid,
    ),
    description: str = typer.Option(
        "", "--description", help="Branch description"
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Issue the mutation (default: dry-run plan only)",
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
    """Create a Global Branch (plan-first; --apply currently blocked).

    Backed by branch-service ``POST /branch/create``. 2026-07-24
    contract-recovery validation on a live Foundry deployment identified the request fields
    ``{displayName, description, ontologyRid}`` but the request never
    progressed past ``400 Default:InvalidArgument`` -- the contract is NOT
    verified end-to-end, so ``--apply`` refuses rather than guessing.

    Without ``--apply`` the command prints the dry-run plan and issues no
    network request.
    """
    service = GlobalBranchService(profile=profile)
    plan = service.plan_create_branch(display_name, description, ontology_rid)

    if not apply:
        if agent_mode_enabled() or format == "agent":
            buffer_agent_payload(
                plan,
                meta={
                    "operation": "create_global_branch",
                    "mode": "plan",
                    "shape_verified": False,
                    "write_verified": False,
                },
            )
        else:
            formatter.format_output([plan], format, output)
        return

    message = (
        "create_global_branch write contract UNVERIFIED: "
        f"{GlobalBranchService.CREATE_CONTRACT} "
        "Not issuing the mutation. Evidence: the captured contract"
    )
    if agent_mode_enabled() or format == "agent":
        buffer_agent_payload(
            plan,
            meta={
                "operation": "create_global_branch",
                "mode": "blocked",
                "shape_verified": False,
                "write_verified": False,
            },
            errors=[{"type": "unverified-write-contract", "message": message}],
        )
    else:
        console.print(f"[red]{message}[/red]")
    raise typer.Exit(1)


@app.command("close")
def close_branch(
    branch_rid: str = typer.Argument(
        ..., help="Global Branch Resource Identifier", autocompletion=complete_rid
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Issue the mutation (default: dry-run plan only)",
    ),
    yes: bool = typer.Option(
        False, "--yes", help="Confirm the destructive close (required with --apply)"
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
    """Close a Global Branch (DESTRUCTIVE; plan-first).

    Backed by branch-service ``PUT /branch/close/{branchRid}`` (empty-body
    write; error contract contract-verified, success shape
    UNVERIFIED and passed through raw). Without ``--apply`` the command
    prints the dry-run plan and issues no network request. The real close
    requires both ``--apply`` and ``--yes``.
    """
    try:
        cache_rid(branch_rid)
        service = GlobalBranchService(profile=profile)

        if not apply:
            plan = {
                "mode": "plan",
                "request": {
                    "verb": "PUT",
                    "path": f"/branch-service/api/branch/close/{branch_rid}",
                    "body": {},
                },
                "contract": GlobalBranchService.CLOSE_CONTRACT,
            }
            if agent_mode_enabled() or format == "agent":
                buffer_agent_payload(
                    plan,
                    meta={
                        "operation": "close_global_branch",
                        "branch_rid": branch_rid,
                        "mode": "plan",
                        "shape_verified": False,
                    },
                )
            else:
                formatter.format_output([plan], format, output)
            return

        if not require_confirmation(
            f"Close global branch {branch_rid}? This is destructive.",
            confirmed=yes,
            option_name="--yes",
        ):
            console.print("[yellow]Close cancelled[/yellow]")
            raise typer.Exit(1)
        with SpinnerProgressTracker().track_spinner(
            f"Closing global branch {branch_rid}..."
        ):
            result = service.close_branch(branch_rid)

        if agent_mode_enabled() or format == "agent":
            buffer_agent_payload(
                result,
                meta={
                    "operation": "close_global_branch",
                    "branch_rid": branch_rid,
                    "mode": "applied",
                    "shape_verified": False,
                },
            )
        else:
            formatter.format_output([result], format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except (GlobalBranchNotFoundError, GlobalBranchShapeError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error closing global branch: {e}[/red]")
        raise typer.Exit(1)
